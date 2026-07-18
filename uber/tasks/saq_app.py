import asyncio
import inspect
import logging
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union

import time

import redis
from aiolimiter import AsyncLimiter
from saq import Queue, Worker

from uber.config import c, _config as config_dict

log = logging.getLogger(__name__)

# Alias for backward compatibility across modules
AsyncRateLimiter = AsyncLimiter


def schedule_to_cron(schedule: Any) -> Optional[str]:
    """
    Converts Celery timedelta or crontab objects into a standard 5-field cron expression for SAQ.
    """
    if isinstance(schedule, str):
        return schedule
    elif isinstance(schedule, timedelta):
        total_seconds = int(schedule.total_seconds())
        if total_seconds < 60:
            return "* * * * *"
        minutes = total_seconds // 60
        if minutes < 60:
            return f"*/{minutes} * * * *"
        hours = minutes // 60
        if hours < 24:
            return f"0 */{hours} * * *"
        days = hours // 24
        return f"0 0 */{days} * *"
    elif isinstance(schedule, crontab):
        minute = str(schedule._orig_minute if hasattr(schedule, '_orig_minute') else schedule.minute)
        hour = str(schedule._orig_hour if hasattr(schedule, '_orig_hour') else schedule.hour)
        day_of_month = str(schedule._orig_day_of_month if hasattr(schedule, '_orig_day_of_month') else schedule.day_of_month)
        month = str(schedule._orig_month_of_year if hasattr(schedule, '_orig_month_of_year') else schedule.month_of_year)
        day_of_week = str(schedule._orig_day_of_week if hasattr(schedule, '_orig_day_of_week') else schedule.day_of_week)
        return f"{minute} {hour} {day_of_month} {month} {day_of_week}"
    return None


class SAQApp:
    """
    Simple Async Queue (SAQ) manager for Ubersystem.
    Provides native asyncio background job execution, cron scheduling, and backward-compatible .delay() dispatching.
    """

    def __init__(self, name: str = "uber_saq"):
        self.name = name
        self.registered_functions: Dict[str, Callable] = {}
        self.cron_jobs: List[Dict[str, Any]] = []
        self._queue: Optional[Queue] = None

    @property
    def redis_url(self) -> str:
        host = c.REDISCONF.get('host', 'localhost')
        port = c.REDISCONF.get('port', 6379)
        db = c.REDISCONF.get('db', 0)
        return f"redis://{host}:{port}/{db}"

    @property
    def queue(self) -> Queue:
        if self._queue is None:
            self._queue = Queue.from_url(self.redis_url, name=self.name)
        return self._queue

    def task(self, fn: Callable) -> Callable:
        """
        Decorator to register a task function for SAQ execution.
        Equips the function with a .delay(*args, **kwargs) method for seamless backward compatibility.
        """
        func_name = fn.__name__
        is_coroutine = inspect.iscoroutinefunction(fn)

        async def saq_job_handler(ctx: Dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            # Check if original function expects ctx
            sig = inspect.signature(fn)
            params = list(sig.parameters.keys())
            
            if params and params[0] in ('ctx', 'context'):
                call_args = (ctx, *args)
            else:
                call_args = args

            if is_coroutine:
                return await fn(*call_args, **kwargs)
            else:
                # Execute synchronous legacy functions in a worker thread to prevent event loop blocking
                return await asyncio.to_thread(fn, *call_args, **kwargs)

        saq_job_handler.__name__ = func_name
        self.registered_functions[func_name] = saq_job_handler

        def delay(*args: Any, **kwargs: Any) -> Any:
            """
            Synchronous .delay() helper to enqueue jobs from web controllers or Celery tasks into SAQ.
            """
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                return asyncio.create_task(self.queue.enqueue(func_name, *args, **kwargs))
            else:
                return asyncio.run(self.queue.enqueue(func_name, *args, **kwargs))

        fn.delay = delay
        fn.saq_handler = saq_job_handler
        return fn

    def schedule(self, schedule_spec: Any, *args: Any, **kwargs: Any) -> Callable:
        """
        Decorator to register periodic cron tasks for SAQ execution.
        """
        def decorator(fn: Callable) -> Callable:
            registered_fn = self.task(fn)
            cron_str = schedule_to_cron(schedule_spec)
            if cron_str:
                self.cron_jobs.append({
                    "function": registered_fn.saq_handler,
                    "cron": cron_str,
                    "args": args,
                    "kwargs": kwargs,
                })
            return registered_fn
        return decorator

    def get_worker(self, concurrency: int = 20) -> Worker:
        """
        Constructs and returns an SAQ Worker configured with all registered tasks and cron schedules.
        """
        return Worker(
            queue=self.queue,
            functions=list(self.registered_functions.values()),
            cron_jobs=self.cron_jobs,
            concurrency=concurrency,
            startup=self._on_worker_startup,
        )

    async def _on_worker_startup(self, ctx: Dict[str, Any]) -> None:
        log.info(f"🚀 SAQ Async Worker started. Registered {len(self.registered_functions)} tasks and {len(self.cron_jobs)} cron jobs.")


saq_app = SAQApp()
