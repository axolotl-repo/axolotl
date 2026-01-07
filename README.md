# Axolotl
Axolotl stands for "Automatically fiX prOgrams' fauLt On The fLy"

Axolotl is a tool that automatically repairs programs in runtime.

## Environment
* Python 3.8+
* Anaconda

Axolotl is tested on Ubuntu 22.04.5 with Python 3.8 and Anaconda v24.11.3

### CRIU
Axolotl needs `criu` to generate the checkpoint of the program. Use `apt` to install it:
```bash
sudo apt-get install criu
```
### Conda
Axolotl needs 'Anaconda / Miniconda' for setting benchmark and llm-server
- [Installation Guide](https://docs.anaconda.com/free/anaconda/install/index.html)

## Quick Start

To reproduce the results, we provide a 3-step script process. Please ensure **CRIU** and **Conda** are installed on your system before starting.

### Step 1: Start LLM Server
The server handles LLM requests. It requires an API key(use gpt5.2 by default) and stays active until you change the model or stop it. We recommend running this in a separate terminal.

```bash
./scripts/run_llm_server.sh --api_key YOUR_API_KEY
```

### Step 2: Environment Setup for Target Bug
This script creates a Conda environment, checks out the buggy version, and installs Axolotl.

```bash
./scripts/environ_setting.sh -p black -i 17
```

### Step 3: Run Benchmark with Axolotl(Sudo Required)
Run the actual experiment using CRIU. You must provide the LLM server address.

```bash
sudo -E env "PATH=$PATH" bash ./scripts/run_benchmark.sh -p black -i 17 -m gpt5
```

### Result Analysis
After executing **Step 3**, Axolotl monitors the target program and performs runtime repair.
1. **Interception**: The program runs until an unhandled exception occurs. Axolotl pauses the process using **CRIU**.
2. **Patch Generation**: The LLM analyzes the context and generates a patch.
3. **Restore & Resume**: After validation, the process is **restored** to the state immediately before the exception. The patch is applied dynamically, allowing the program to continue execution successfully.

> **Example (black-17)**: This benchmark targets a failing unit test. Axolotl intercepts the initial failure, repairs the code, and allows the test to pass upon restoration.

### Output Directory Structure
The results are stored in `results/{project}/{bug_id}/{model_name}/`.

```text
results/
└── black/
    └── 17/
        └── gpt/
            ├── log/
            │   ├── axolotl_debug.log   # Main workflow logs
            │   └── time_profile.json   # Execution time of each parts
            └── model_interaction/      # LLM API logs
                ├── gen_patch_0.json
                ├── fault_localize_0.json
                └── ...

