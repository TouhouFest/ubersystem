from residue import UUID
from sqlalchemy import String
from sqlalchemy.schema import ForeignKey, Index, Table, UniqueConstraint

from uber.models import MagModel
from uber.models.types import DefaultColumn as Column

__all__ = ['Upload']

upload_association = Table(
    'model_upload',
    MagModel.metadata,
    Column('model_id', UUID, ForeignKey('group.id')),
    Column('upload_id', UUID, ForeignKey('upload.id')),
    UniqueConstraint('upload_id'),
    Index('ix_model_upload_model_id', 'model_id'),
    Index('ix_model_upload_upload_id', 'upload_id')
)


class Upload(MagModel):
    mime = Column(String)
