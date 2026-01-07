# BugsInPy++

BugsInPy++ improves the scalability, reproducibility, and usability of the BugsInPy dataset.
It is based on the modified BugsInPy by F. Aguilar, S. Grayson and D. Marinov.
Below is the citation for the modified BugsInPy:

```
F. Aguilar, S. Grayson and D. Marinov, "Reproducing and Improving the BugsInPy Dataset," 2023 IEEE 23rd International Working Conference on Source Code Analysis and Manipulation (SCAM), Bogotá, Colombia, 2023, pp. 260-264, doi: 10.1109/SCAM59687.2023.00036.
```

Here is the repository of the modified BugsInPy by them:
```
https://github.com/reproducing-research-projects/BugsInPy
```

They did fantastic work on the BugsInPy dataset, but it has some limitations:
* It's scripts assume that the user uses their own Dockerfile. Thus, some file paths are hardcoded.
* Their conda environments use hash as a name, which is not very user friendly.
* Outputs of the tests are user friendly, but not machine friendly.
* Log messages are not enough to understand what is going on.
* If the conda environment is not existing, the script will fail.

Therefore, we fixed and improved these issues:
* The scripts can accept some environment variables to make it more flexible. See [Environment Variables](#enviromnment-variables) section.
* Now the conda environments are named with the project name and the bug id (e.g. `youtube-dl_1`).
  This makes it easier to understand which environment is used for which project and bug.
* The outputs of the tests are now more machine friendly. See [Test results](#test-results) section.
* The log messages are optimized.
* `bugsinpy-compile` will create the conda environment if it does not exist.
  The other scripts for the testing will still fail to force the user to run `bugsinpy-compile` first.

## Environment
* Python 3.8+
* Anaconda or Miniconda

BugsInPy++ is tested on Ubuntu 22.04 with Python 3.10 and Anaconda 2024.10.

Additionally, run following commands to install the required packages:
```bash
apt-get update
apt-get install -y git nano dos2unix build-essential
```

## Steps to set up BugsInPy
First, clone BugsInPy repository:

Then, add the BugsInPy executables path to your `PATH` environment variable:
```bash
export PATH=$PATH:<bugsinpy_path>/framework/bin
```
In most cases, you can add this line to your `~/.bashrc`, `~/.bash_aliases` or `~/.bash_profile` file to make it permanent.

That's it! Now you can use the BugsInPy commands from anywhere in your terminal.

## BugsInPy Command

| Command  | Description                                                                                                           |
| -------- | --------------------------------------------------------------------------------------------------------------------- |
| info     | Get the information of a specific project or a specific bug                                                           |
| checkout | Checkout buggy or fixed version project from dataset                                                                  |
| compile  | Compile sources from project that have been checkout                                                                  |
| test     | Run test case that relevant with bug, single-test case from input user, or all test cases from project                |
| coverage | Run code coverage analysis from test case that relevant with bug, single-test case from input user, or all test cases |
| mutation | Run mutation analysis from input user or test case that relevant with bug                                             |
| fuzz     | Run a test input generation from specific bug                                                                         |
| testall  | Reproduce all bugs buggy and fixed version for all projects                                                           |

## Usage of BugsInPy
### Print help usage
```bash
bugsinpy-<command> --help
```
For example, run
```bash
bugsinpy-info --help
```
to print the help usage of `bugsinpy-info` command.

### Checkout a specific bug:
```
bugsinpy-checkout -p <project_name> -b <bug_id> -v <0/1> -w <workspace>
```
- `-p <project_name>`: Name of the project (e.g. youtube-dl).
- `-b <bug_id>`: Bug ID (e.g. 1).
- `-v <0/1>`: Buggy (0) or fixed (1) version.
- `-w <workspace>`: Workspace name in **absolute path** (e.g. $PWD/youtube-dl_1).

For example, to checkout the buggy version of bug 1 from the youtube-dl project, run:
```bash
bugsinpy-checkout -p youtube-dl -b 1 -v 0 -w $PWD/youtube-dl_1
```

### Compile the project:
```bash
bugsinpy-compile [-w <workspace>]
```
* `-w <workspace>`: Optional workspace name (e.g. youtube-dl_1). Default is current directory.

:warning: Running `bugsinpy-compile` in parallel may cause issue related to `urllib3` package.

For example to compile the project we checked out in the previous step, run:
```bash
bugsinpy-compile -w youtube-dl_1
```
or
```bash
cd youtube-dl_1
bugsinpy-compile
```

### Test the project:
```bash
bugsinpy-test [-w <workspace>] [-t <test_case>] [-a]
```
* `-w <workspace>`: Optional workspace name (e.g. youtube-dl_1). Default is current directory.
* `-t <test_case>`: Run single test instead of all *relevant* tests.
  Format of the test case is dependent on the testing framework used in the project. To check the format, run `bugsinpy-test --help`.
* `-a`: Run all test cases instead of the *relevant* tests.

For example, to run relevant tests for the project we compiled in the previous step, run:
```bash
bugsinpy-test -w youtube-dl_1
```
or
```bash
cd youtube-dl_1
bugsinpy-test
```

To run a test whose ID is `test.test_utils.TestUtil.test_match_str`, run:
```bash
bugsinpy-test -w youtube-dl_1 -t test.test_utils.TestUtil.test_match_str
```

To run all tests, run:
```bash
bugsinpy-test -w youtube-dl_1 -a
```

### Test results
#### Relevant tests
After running *relevant* tests (i.e. default mode), the test results will be stored in the `<workspace>/bugsinpy_test.txt` file.
In the file, it stores the results of the each test in the following format:
```
BugsInPy test: <test_command>: <return_code>
```
Where `<test_command>` is the command used to run the test and `<return_code>` is the return code of the command.

In addition, the stdout and stderr of the command will be stored.

Also, it prints the results to the console in the same format, but without the stdout and stderr from the command.

#### Single test
After running a single test, the test results will be stored in the `<workspace>/bugsinpy_singletest.txt` file with the same format as above.

#### All tests
After running all tests, the test results will be stored in the `<workspace>/bugsinpy_alltest.txt` file.
However, the format is different from the relevant tests and single test. It is dependent on the testing framework used in the project.

## Enviromnment Variables
* `CONDA_PATH`: Root path of conda installation. Default is `$HOME/anaconda3`.

<!-- ## Example BugsInPy Docker

The docker enviroments make sure all the dependencies and specific python versions are met by using the [miniconda3 image](https://hub.docker.com/r/continuumio/miniconda3)

Prerequisite is `docker` and `docker compose` please see [documentation](https://docs.docker.com/engine/install/)

- Remove previous index and cleanup old containers before a new run:
  - `rm projects/bugsinpy-index.csv`
  - `docker compose down`
- Reproduce all the bugs in a specific project:
  - `docker compose up setup youtube-dl --build`
- Reproduce all projects bugs running buggy (0) and fixed (1) versions
  - ⚠️ Reproduce all projects may require a lot of resources, tested successfully on 4 cores 8 RAM 100GB free drive space
  - `docker compose up --build` -->

## New script: `bugsinpy-testall`

The `bugsinpy-testall` script automates the execution of the BugsInPy dataset, which contains bugs in various Python projects.
The script reproduces the bugs, executes tests, and records the results.
It enhances the reproducibility of Python projects by providing a standardized process for reproducing and testing bugs in different projects.

Here's a summary of how the script works:

1. The script takes command-line arguments to control its behavior. It provides options to display help, perform cleanup, and specify projects or ranges of bugs to reproduce and test.

2. It creates a `temp/projects` directory to store the output and logs.

3. The script iterates over the specified projects or all projects in the `BugsInPy/projects` directory.

4. For each project, it determines the range of bugs to reproduce and test.

5. It executes the tests for each bug by performing the following steps:
   a. Checks if the bug has already been tested and skips it if so.
   b. Sets up the environment for testing the buggy (0) version:
      - Uses `bugsinpy-checkout` to checkout the buggy version.
      - Activates the proper Python environment using Miniconda (specified in the `bugsinpy_bug.info` file).
      - Compiles the project (if required) and runs the tests using `bugsinpy-test`.
      - Check if the buggy version fails as expected for the test specific to the bug and save the output in the `BugsInPy/projects/<repo>/bugs/<bugid>/bug_buggy.txt`.
      - Updates the `BugsInPy/projects/bugsinpy-index.csv` with the results `<repo>,<bugid>,buggy,fail`
   c. The it proceeds to test the fixed (1) version:
      - Uses `bugsinpy-checkout` to checkout the fixed version.
      - Compiles the project (if required) and runs the tests.
      - Activates the proper Python environment using Miniconda (specified in the `bugsinpy_bug.info` file).
      - Compiles the project (if required) and runs the tests using `bugsinpy-test`.
      - Check if the fixed version pass as expected for the test specific to the bug and save the output in the `BugsInPy/projects/<repo>/bugs/<bugid>/bug_fixed.txt`.
      - Updates the `BugsInPy/projects/bugsinpy-index.csv` with the results `<repo>,<bugid>,fixed,pass`

6. The script deactivates the Conda environment and repeats the process for the next bug in the project.

The `bugsinpy-testall` script improves reproducibility by providing a standardized and automated approach to reproduce and test bugs in Python projects. It ensures that bugs are tested consistently across different projects, enabling easier verification of bug fixes and facilitating the replication of test results. By logging the output and test results, it helps track the status of bug reproduction and provides a central record for analysis and further investigation.