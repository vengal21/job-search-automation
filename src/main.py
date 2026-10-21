import json
import re
from pathlib import Path
import traceback
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
import undetected_chromedriver as uc
from lib_resume_builder_AIHawk import (
    Resume,
    FacadeManager,
    ResumeGenerator,
    StyleManager,
)
from typing import Optional
from bot_facade import AIHawkBotFacade
from constants import (
    COLLECT_MODE,
    OUTPUT_FIELE_DIRECTORY,
    PLAIN_TEXT_RESUME_YAML,
    SECRETS_YAML,
    UPLOADS,
    WORK_PREFERENCES_YAML,
    WORK_PREFERENCES,
)
from job_manager import AIHawkJobManager
from llm.ai_answerer import AiAnswerer
from utils.chrome_utils import chrome_browser_options

from job_application_profile import JobApplicationProfile
from logger import logger
from utils import browser_utils





class ConfigError(Exception):
    pass


class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        return (
            re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email)
            is not None
        )

    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, "r") as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")

    @staticmethod
    def validate_work_preferences(work_preferences_file: Path) -> dict:

        parameters = ConfigValidator.validate_yaml_file(work_preferences_file)

        required_keys = {
            "remote": bool,
            "experience_level": dict,
            "job_types": dict,
            "date": dict,
            "positions": list,
            "locations": list,
            "location_blacklist": list,
            "distance": int,
            "company_blacklist": list,
            "title_blacklist": list,
            "keywords_whitelist": list,
        }

        for key, expected_type in required_keys.items():
            if key not in parameters:
                if key in [
                    "company_blacklist",
                    "title_blacklist",
                    "location_blacklist",
                ]:
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Missing or invalid key '{key}' in config file {work_preferences_file}"
                    )
            elif not isinstance(parameters[key], expected_type):
                if (
                    key
                    in ["company_blacklist", "title_blacklist", "location_blacklist"]
                    and parameters[key] is None
                ):
                    parameters[key] = []
                else:
                    raise ConfigError(
                        f"Invalid type for key '{key}' in config file {work_preferences_file}. Expected {expected_type}."
                    )

        # Validate experience levels, ensure they are boolean
        experience_levels = [
            "internship",
            "entry",
            "associate",
            "mid_senior_level",
            "director",
            "executive",
        ]
        for level in experience_levels:
            if not isinstance(parameters["experience_level"].get(level), bool):
                raise ConfigError(
                    f"Experience level '{level}' must be a boolean in config file {work_preferences_file}"
                )

        # Validate job types, ensure they are boolean
        job_types = [
            "full_time",
            "contract",
            "part_time",
            "temporary",
            "internship",
            "other",
            "volunteer",
        ]
        for job_type in job_types:
            if not isinstance(parameters["job_types"].get(job_type), bool):
                raise ConfigError(
                    f"Job type '{job_type}' must be a boolean in config file {work_preferences_file}"
                )

        # Validate date filters
        date_filters = ["all_time", "month", "week", "24_hours"]
        for date_filter in date_filters:
            if not isinstance(parameters["date"].get(date_filter), bool):
                raise ConfigError(
                    f"Date filter '{date_filter}' must be a boolean in config file {work_preferences_file}"
                )

        # Validate positions and locations as lists of strings
        if not all(isinstance(pos, str) for pos in parameters["positions"]):
            raise ConfigError(
                f"'positions' must be a list of strings in config file {work_preferences_file}"
            )
        if not all(isinstance(loc, str) for loc in parameters["locations"]):
            raise ConfigError(
                f"'locations' must be a list of strings in config file {work_preferences_file}"
            )

        # Validate distance
        approved_distances = {0, 5, 10, 25, 50, 100}
        if parameters["distance"] not in approved_distances:
            raise ConfigError(
                f"Invalid distance value in config file {work_preferences_file}. Must be one of: {approved_distances}"
            )

        # Ensure blacklists are lists
        for blacklist in ["company_blacklist", "title_blacklist", "location_blacklist"]:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(
                    f"'{blacklist}' must be a list in config file {work_preferences_file}"
                )
            if parameters[blacklist] is None:
                parameters[blacklist] = []

        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> str:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        mandatory_secrets = ["llm_api_key"]

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(
                    f"Missing secret '{secret}' in file {secrets_yaml_path}"
                )

        if not secrets["llm_api_key"]:
            raise ConfigError(
                f"llm_api_key cannot be empty in secrets file {secrets_yaml_path}."
            )
        return secrets["llm_api_key"]


class FileManager:
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = [SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML]
        missing_files = [
            file for file in required_files if not (app_data_folder / file).exists()
        ]

        if missing_files:
            raise FileNotFoundError(
                f"Missing files in the data folder: {', '.join(missing_files)}"
            )

        output_folder = app_data_folder / "output"
        output_folder.mkdir(exist_ok=True)
        return (
            app_data_folder / SECRETS_YAML,
            app_data_folder / WORK_PREFERENCES_YAML,
            app_data_folder / PLAIN_TEXT_RESUME_YAML,
            output_folder,
        )

    @staticmethod
    def file_paths_to_dict(
        resume_file: Path | None, plain_text_resume_file: Path
    ) -> dict:
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(
                f"Plain text resume file not found: {plain_text_resume_file}"
            )

        result = {"plainTextResume": plain_text_resume_file}

        if resume_file:
            if not resume_file.exists():
                raise FileNotFoundError(f"Resume file not found: {resume_file}")
            result["resume"] = resume_file

        return result


def init_browser() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        return uc.Chrome(options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")


def create_and_run_bot(parameters, llm_api_key, selected_jobs=None):
    raise RuntimeError(
        "Job collection and application are unavailable because the previous board "
        "integration was removed. Configure an authorized replacement job source, "
        "job-description parser, board login (if needed), and application-form adapter."
    )


@click.command()
@click.option(
    "--resume",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Path to the resume PDF file",
)
@click.option(
    "--collect",
    is_flag=True,
    help="Only collects data job information into data.json file",
)
@click.option(
    "--apply-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    help="Apply only jobs in a dashboard selection JSON file",
)
def main(collect: bool = False, resume: Optional[Path] = None, apply_file: Optional[Path] = None):
    try:
        if collect and apply_file:
            raise click.UsageError("--collect and --apply-file cannot be used together")
        data_folder = Path("data_folder")
        secrets_file, work_preferences_file, plain_text_resume_file, output_folder = (
            FileManager.validate_data_folder(data_folder)
        )
        parameters = {}
        parameters[WORK_PREFERENCES] = ConfigValidator.validate_work_preferences(work_preferences_file)
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)

        parameters[UPLOADS] = FileManager.file_paths_to_dict(
            resume, plain_text_resume_file
        )
        parameters[OUTPUT_FIELE_DIRECTORY] = output_folder
        parameters[COLLECT_MODE] = collect

        selected_jobs = None
        if apply_file:
            from job import Job
            with apply_file.open("r", encoding="utf-8") as stream:
                requested = yaml.safe_load(stream)
            collected_path = output_folder / "data.json"
            collected = json.loads(collected_path.read_text(encoding="utf-8")) if collected_path.exists() else []
            available = {str(row.get("link", "")): row for row in collected if row.get("link")}
            if not isinstance(requested, list) or not 1 <= len(requested) <= 100:
                raise click.ClickException("Select between 1 and 100 jobs")
            selected_jobs = []
            for row in requested:
                link = str(row.get("link", ""))
                if link not in available:
                    raise click.ClickException("A selected job is no longer in the collected job list")
                selected_jobs.append(Job(**{k: v for k, v in available[link].items() if k in Job.__dataclass_fields__}))
        create_and_run_bot(parameters, llm_api_key, selected_jobs)
    except ConfigError as ce:
        logger.error(f"Configuration error: {str(ce)}")
        logger.error(
            f"Configuration error: {str(ce)}. Check your config files and ensure all required fields are present."
        )

    except FileNotFoundError as fnf:
        logger.error(f"File not found: {str(fnf)}")
        logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        logger.error(f"Runtime error: {str(re)} {traceback.format_exc()}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()
