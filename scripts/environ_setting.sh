#!/bin/bash
set -e

# Usage:
# ./environ_setting.sh -p black -i 17
usage="
        -p project_name
             The name of the project for which a particular version shall be checked out. Run bugsinpy-info to check available project
        -i bug_id
             The number of bug from project in bugsinpy. Run bugsinpy-info to check bug id number
"

export PYTHONNOUSERSITE=1

# argument parsing
while getopts p:i: flag; do
    case "${flag}" in
        p) project_name=${OPTARG} ;;
        i) bug_id=${OPTARG} ;;
        *) echo "$usage"; exit 1 ;;
    esac
done

if [ -z "$project_name" ] || [ -z "$bug_id" ]; then
    echo "Error: Missing arguments."
    echo "$usage"
    exit 1
fi

# Path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # ->  /axolotl(root)/scripts
Root_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"               # ->  /axolotl(root)
BENCH_DIR="$(cd "$SCRIPT_DIR/../benchmarks" && pwd)"        # ->  /axolotl(root)/benchmarks
BUGSINPY_DIR="$(cd "$SCRIPT_DIR/../BugsInPyPP" && pwd)"     # ->  /axolotl(root)/BugsInPyPP

BASE_WORK_DIR="$BENCH_DIR/$project_name/$bug_id/buggy"       # ->  /axolotl(root)/benchmarks/<project_name>/<bug_id>/buggy
REPO_DIR="$BASE_WORK_DIR/$project_name"                      # ->  /axolotl(root)/benchmarks/<project_name>/<bug_id>/buggy/<project_name>           

echo "================================================================================="
echo " Setting up Environment for $project_name-$bug_id (Buggy Version)"
echo " Work Dir: $BASE_WORK_DIR"
echo "================================================================================="

if [ ! -d "$BASE_WORK_DIR" ]; then
    mkdir -p "$BASE_WORK_DIR"
fi

##Check if project_info exist
PROJECT_INFO_DIR="$BUGSINPY_DIR/projects/$project_name"
if [ ! -d "$PROJECT_INFO_DIR" ]; then
    echo "Error: Project $project_name not found in BugsInPyPP."
    exit 1
fi

input="$PROJECT_INFO_DIR/project.info"
githubURL=""
while IFS= read -r line; do
    if [[ "$line" == "github_url="* ]]; then
        githubURL="$(cut -d'"' -f 2 <<< $line)"
    fi
done < "$input"

## git clone
if [ -d "$REPO_DIR" ]; then
    echo "Repository already exists. Skipping clone..."
else
    git clone "$githubURL" "$REPO_DIR"
fi

BUG_INFO_DIR="$PROJECT_INFO_DIR/bugs/$bug_id"
buggy_commit=""
fix_commit=""
test_file_arr=()
pythonpath_val=""

DONE=false
until $DONE; do
    read || DONE=true
    if [[ "$REPLY" == "buggy_commit_id"* ]]; then
        buggy_commit="$(cut -d'"' -f 2 <<< $REPLY)"
    elif [[ "$REPLY" == "fixed_commit_id"* ]]; then
        fix_commit="$(cut -d'"' -f 2 <<< $REPLY)"
    elif [[ "$REPLY" == "test_file"* ]]; then
        test_file_str="$(cut -d'"' -f 2 <<< $REPLY)"
        IFS=';' read -r -a test_file_arr <<< "$test_file_str"
    elif [[ "$REPLY" == "pythonpath"* ]]; then
        # Compile 스크립트 로직 반영: PythonPath 파싱
        pythonpath_val="$(cut -d'"' -f 2 <<< $REPLY)"
    fi
done < "$BUG_INFO_DIR/bug.info"

# checkout
cd "$REPO_DIR"

git reset --hard "$fix_commit" > /dev/null
TEMP_TEST_DIR=$(mktemp -d)
for test_file in "${test_file_arr[@]}"; do
    if [ -f "$test_file" ]; then
        cp --parents "$test_file" "$TEMP_TEST_DIR"
    fi
done

git reset --hard "$buggy_commit" > /dev/null
git clean -f -d > /dev/null
rm -rf env/

if [ -d "$TEMP_TEST_DIR" ]; then
    cp -rf "$TEMP_TEST_DIR/." . 
    rm -rf "$TEMP_TEST_DIR"
fi

cp -f "$BUG_INFO_DIR/bug.info" "$REPO_DIR/bugsinpy_bug.info"
cp -f "$BUG_INFO_DIR/requirements.txt" "$REPO_DIR/bugsinpy_requirements.txt"
cp -f "$BUG_INFO_DIR/run_test.sh" "$REPO_DIR/bugsinpy_run_test.sh"
if [ -f "$BUG_INFO_DIR/setup.sh" ]; then
    cp -f "$BUG_INFO_DIR/setup.sh" "$REPO_DIR/bugsinpy_setup.sh"
fi

################################################################################
## phase 2 : create conda environment
################################################################################
default_conda_path=$HOME/anaconda3
conda_path="${CONDA_PATH:-$default_conda_path}"
if [ -f "$conda_path/etc/profile.d/conda.sh" ]; then
    source "$conda_path/etc/profile.d/conda.sh"
fi

if [ -f "$REPO_DIR/bugsinpy_requirements.txt" ]; then
    sed -i -e '/^\s*#.*$/d' -e '/^\s*$/d' "$REPO_DIR/bugsinpy_requirements.txt"
    if command -v dos2unix &> /dev/null; then
        dos2unix "$REPO_DIR/bugsinpy_requirements.txt" &> /dev/null
    fi
fi

bug_python_version=$(grep -o "3\..\.." "$REPO_DIR/bugsinpy_bug.info" || echo "3.8")
env_name="${project_name}_${bug_id}"

if conda env list | grep -qE "^$env_name\s"; then
    echo "Removing existing environment: $env_name"
    conda remove -n "$env_name" --all -y
fi

echo "Creating environment $env_name (Python $bug_python_version)..."
conda create -n "$env_name" -y python="$bug_python_version"

if ! conda activate "$env_name"; then
    echo "Failed to activate conda environment $env_name"
    exit 1
fi

if [ -n "$pythonpath_val" ]; then
    IFS=';' read -r -a p_paths <<< "$pythonpath_val"
    full_pythonpath=""
    for p_path in "${p_paths[@]}"; do
        full_pythonpath="$REPO_DIR/$p_path:$full_pythonpath"
    done
    
    echo "Setting PYTHONPATH to $full_pythonpath"
    export PYTHONPATH="$full_pythonpath$PYTHONPATH"
    conda env config vars set PYTHONPATH="$full_pythonpath"
fi

echo "Installing dependencies..."
pip install --upgrade pip
pip install --upgrade typing_extensions

case "$project_name" in
    "pandas")
        export CFLAGS="-Wno-error=array-bounds"
        pip install setuptools==66.1.1
        ;;
esac

if [ -f "$REPO_DIR/bugsinpy_requirements.txt" ] && grep -q '[^[:space:]]' "$REPO_DIR/bugsinpy_requirements.txt"; then
    sed -e '/^\s*#.*$/d' -e '/^\s*$/d' "$REPO_DIR/bugsinpy_requirements.txt" | xargs -I {} pip install {} || true
else
    echo "No special dependencies found or file empty."
fi

echo "================================================================================="
echo " [Phase 3] Compile & Install Project"
echo "================================================================================="

if [ -f "$REPO_DIR/bugsinpy_setup.sh" ]; then
    echo "Running setup script..."
    bash "$REPO_DIR/bugsinpy_setup.sh"
fi

if [ -f "$REPO_DIR/bugsinpy_install.sh" ]; then
    echo "Running install script..."
    while IFS= read -r line || [ -n "$line" ]; do
        cmd=$(echo "$line" | sed -e 's/\r//g')
        [ -n "$cmd" ] && eval "$cmd"
    done < "$REPO_DIR/bugsinpy_install.sh"
fi

echo "1" > "$REPO_DIR/bugsinpy_compile_flag"
echo "Created bugsinpy_compile_flag."

if [ -f "setup.py" ] || [ -f "pyproject.toml" ]; then
    echo "Installing project in editable mode..."
    pip install -e . || echo "Warning: pip install -e failed, continuing..."
fi


if [ -f "$REPO_DIR/bugsinpy_requirements.txt" ]; then
    pip install -r "$REPO_DIR/bugsinpy_requirements.txt"
fi

## install axolotl
echo "Installing Axolotl..."
cd "$Root_DIR"
pip install .

echo "================================================================================="
echo " [Success] All Setup Completed!"
echo " Project: $project_name-$bug_id"
echo " Environment: $env_name"
echo " Location: $REPO_DIR"
echo "================================================================================="

conda deactivate

