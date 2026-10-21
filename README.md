<a name="top"></a>
<div align="center">

# Gogoi

<!-- for testing purpose on vs code -->
<!-- <video src="docs/Job Search Assistant demo.mp4" 
       width="1280" 
       height="720" 
       controls 
       onloadeddata="this.playbackRate = 2">
</video> -->

[job search assistant demo](https://github.com/user-attachments/assets/3cb23ee2-5128-4045-adfb-c90ad5b16611)

<!-- Temporarity commented test suite branch and testing CI/CD is not working, doing manual testing as of now -->
**🤖 Gogoi helps Vengal find matching jobs and prepare applications for review. You sign in, review each form, and submit it yourself.**

</div>

[Special thanks](#special-thanks) 

Gogoi is Vengal's job-search assistant. See the project documentation below for setup and operation.

[Project Management Documentation](docs/project_management.md)
 

## Table of Contents

1. [Introduction](#introduction)
2. [Features](#features)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Usage](#usage)
6. [Documentation](#documentation)
7. [Troubleshooting](#troubleshooting)
8. [Conclusion](#conclusion)
9. [Contributors](#contributors)
10. [License](#license)
11. [Disclaimer](#disclaimer)

## Introduction

Gogoi searches public job listings against Vengal's profile, then prepares selected applications in a visible browser for manual review.

### The Challenge of Modern Job Hunting

In the digital age, the job search landscape has undergone a dramatic transformation. While online platforms have opened up a world of opportunities, they have also intensified competition. Job seekers often find themselves spending countless hours scrolling through listings, tailoring applications, and repetitively filling out forms. This process can be not only time-consuming but also emotionally draining, leading to job search fatigue and missed opportunities.

### Gogoi: Vengal's Personal Job Search Assistant

Gogoi helps reduce repetitive job-search work while leaving each application under Vengal's review.

## Features

1. **Job Search**
   - Customizable search criteria
   - Continuous scanning for new openings
   - Smart filtering to exclude irrelevant listings

2. **Application Preparation**
   - Opens selected postings in a visible browser
   - Fills fields it can match to your saved profile
   - Leaves missing answers and final review to you

3. **AI-Powered Personalization**
   - Dynamic response generation for employer-specific questions
   - Tone and style matching to fit company culture
   - Keyword optimization for improved application relevance

4. **Volume Management with Quality**
   - Bulk application capability
   - Quality control measures
   - Detailed application tracking

5. **Intelligent Filtering and Blacklisting**
   - Company blacklist to avoid unwanted employers
   - Title filtering to focus on relevant positions

6. **Dynamic Resume Generation**
   - Automatically creates tailored resumes for each application
   - Customizes resume content based on job requirements

7. **Secure Data Handling**
   - Manages sensitive information securely using YAML files

## Installation

**Confirmed successful runs on the following:**

- Operating Systems:
  - Windows 10
  - Ubuntu 22
  - macOS
- Python versions:
  - 3.13

## Prerequisites

Before you begin, ensure you have met the following requirements:

### Download and Install Python

Ensure you have the latest Python version installed (Python 3.11 or higher is required for this project). If not, download and install it from Python's official website. For detailed instructions, refer to the tutorials:
- [How to Install Python on Windows](https://docs.python.org/3/using/windows.html)
- [How to Install Python on Linux](https://docs.python.org/3/using/unix.html)
- [How to Download and Install Python on macOS](https://docs.python.org/3/using/mac.html)

### Download and Install Google Chrome

Download and install the latest version of Google Chrome in its default location from the [official website](https://www.google.com/chrome/).

### Install Poetry

Follow the instructions provided on Poetry's [official installation page](https://python-poetry.org/docs/#installation).

### Clone the Repository

```bash
git clone <your-GitHub-repository-url>
cd <your-repository-folder>
```

#### switching to stable versions

Use the Releases page in your own GitHub repository after you publish a release.

```bash
git checkout <tag_name>
```

example:
```bash
git checkout v0.1.0-beta
```

### Setting Up the Project with Poetry

Since the project already includes a `pyproject.toml` file, follow these steps:

#### Install Dependencies

Run the following command in the project directory to install all dependencies specified in `pyproject.toml`:

```bash
poetry install
```

### Create `.env` File

To configure environment variables for the project, create a `.env` file by copying the `.env.template` file provided in the repository. This file will store sensitive information such as API keys and other configuration settings.

```bash
cp .env.template .env
```

After copying, open the `.env` file and fill in the required values. Ensure you do not share this file or commit it to version control, as it contains sensitive information.

### Usage

1. Set up your profile and preferences in `data_folder/plain_text_resume.yaml` and `data_folder/work_preferences.yaml`. Configure the search provider in `data_folder/secrets.yaml` or `.env` as described in [Configuration](docs/configuration.md).
2. Start the complete local workflow by double-clicking `START_JOB_BOT.bat`, or run `src/start_job_bot.py` with the project's virtual-environment Python.
3. In Gogoi's dashboard, search job boards, review the matches, and select postings to prepare.
4. Sign in yourself in the visible browser. Gogoi fills fields it can match and stops before Submit. Review the form and submit it yourself, one application at a time.
  
### For troubleshooting refer [this docs](/docs/troubleshooting.md)

### For Developers

- [Contribution Guidelines](docs/CONTRIBUTING.md)

- [Lang Chain Developer Documentation](https://python.langchain.com/v0.2/docs/integrations/components/)

- [Workflow diagrams](docs/workflow_diagrams.md)

## Supporting Gogoi

Keep issues, releases, and project tracking in a repository owned by [Vengal](https://github.com/vengal21). Add sponsorship or community links only after configuring accounts owned by Vengal.

For code contributions, see [Contribution Guidelines](docs/CONTRIBUTING.md) and [Project Management](docs/project_management.md).

## License

This project is licensed under the AGPL License. Documentation is licensed under CC BY - see the [AGPL LICENSE](LICENSE) and [CC BY LICENSE](docs/LICENSE) files for details.

The AGPL License requires that any derivative work must also be open source and distributed under the same license.

The CC BY License permits others to distribute, remix, adapt, and build upon your work, even for commercial purposes, as long as they credit you for the original creation. 
 

## Disclaimer

Gogoi is intended for use at your own risk. Follow the terms of service of relevant platforms and review every application before you submit it.

[Back to top 🚀](#top)
