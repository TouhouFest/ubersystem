# Ubersystem Configuration

Ubersystem uses [ConfigObj](https://configobj.readthedocs.io/en/latest/configobj.html) format INI files and environment variables to configure the server.
Event plugins also use ConfigObj and similar environment variables, but prefixed with their name.

ConfigObj uses [ConfigSpec](https://configobj.readthedocs.io/en/latest/configobj.html#configspec) files to validate the configuration at runtime. Ubersystem
and each plugin has a `configspec.ini` file that lists every configuration variable that can be set.

[Ubersystem's configspec.ini](https://github.com/magfest/ubersystem/blob/main/uber/configspec.ini) contains the vast majority of settings, including the event name,
event dates, t-shirt size options, and much much more.

## Loading Configuration
When Ubersystem starts it looks at environment variables to find its configuration.

| Environment Variable | Default Value | Description |
| UBERSYSTEM_CONFIG_FILES | "" | This is an optional list of INI files, separated by semicolons, containing configuration for Ubersystem |
| <plugin name>_CONFIG_FILES | "" | Every additional ubersystem plugin can be configured similarly using this variable with their prefix |

In addition to the file-based method, individual settings may be configured using environment variables.

To find the name of a setting simply concatenate the plugin name with the configuration path, concatenated with `_`.

For example, the following Ubersystem INI file would map to environment variables as shown:
```ini
url_root = /
[cherrypy]
tools.sessions.enabled = True
```

| Environment Variable | Value | Description |
| uber_url_root | / | |
| uber_cherrypy_tools_sessions_enabled | True | |

Note that `.` becomes `_` and the config paths is joined by underscores.

### Environment Variables

### Configuration Files

## Datatypes

## Important Settings

### E-Signature Service Configuration (Switching from SignNow to OpenSign)
Ubersystem supports both **SignNow** (commercial SaaS) and **OpenSign Labs** (open-source cloud / self-hosted Docker) for automated electronic signature collection on Dealer Terms & Conditions (`terms_and_conditions`).

By default, when a dealer is accepted into the marketplace, Ubersystem checks `signnow_dealer_template_id`. However, via the `BaseSignatureRequest` and `get_esign_request()` architecture, Ubersystem dynamically routes all document workflows to **OpenSign** whenever an OpenSign template ID is provided.

#### How to Switch to OpenSign
To switch your event from SignNow to OpenSign, configure the following settings in your `config.ini` (`uber.ini`):

```ini
# 1. Provide the OpenSign Template ID (Setting this overrides SignNow automatically)
opensign_dealer_template_id = "your_opensign_template_id_here"
opensign_dealer_folder_id = "optional_opensign_folder_id"

# 2. Configure the API URL and Token
# By default, Ubersystem connects to OpenSign Cloud (https://api.opensignlabs.com/v1).
# If you are running a self-hosted OpenSign Docker container, override the API URL:
opensign_api_url = "https://signing.yourcon.org/v1"

# For local development or non-AWS deployments, provide your static API token directly:
opensign_api_token = "your_static_api_token_here"

# For AWS Production deployments, leave opensign_api_token blank and provide your AWS Secrets Manager secret name:
# Ubersystem will automatically pull, cache, and rotate the API token in Redis every 15 seconds.
aws_opensign_secret_name = "production/opensign/credentials"
```

Once `opensign_dealer_template_id` is set, all frontend templates (`/preregistration/group_members`, `/group_admin/form`, `/group_admin/dealers`), background polling cron tasks (`check_document_signed`), and PDF downloads (`download_esign_document`) will automatically communicate with OpenSign instead of SignNow.

## Generated Configuration
When working on Uber for a specific event, it's best to start with config overrides copied from that event. Some events have their config overrides available in their own repository. In these cases, you can run the `make_config.py` script in the root of this repo, which will download and compile the config you need into ready-made config files.

To run `make_config.py` and other Python scripts, you'll need to download and install [Python 3](https://www.python.org/downloads/). You'll also need to know the URL of the config repo, and the folders in the repo you want to include.

For example, MAGFest's config repo URL is `https://github.com/magfest/terraform-aws-magfest.git`. You will want to use two folders when downloading MAGFest config: the "dev" environment folder, and a folder corresponding to the event and year you need to download. The following example will download and compile config for MAGFest Super 2024:

```bash
python3 make_config.py --repo https://github.com/magfest/terraform-aws-magfest.git --paths uber_config/environments/dev uber_config/events/super/2024
```

These folders are based on the specific folder structure in MAGFest's config repo [explained here](https://github.com/magfest/terraform-aws-magfest/blob/main/uber_config/README.md). Other event's config may be organized differently.

Once you run this Python script, it will download a file of config overrides into the root of this repo called `uber.ini`. It may also download additional `.ini` files corresponding to custom plugins -- these files will be named after the plugin name (e.g., custom config for the magstock plugin will be compiled into `magstock.ini`). Make sure you [download these plugins](DEVELOPERS.md#custom-plugins) and move each file into the root folder of its corresponding repository folder.

## Setting Reference