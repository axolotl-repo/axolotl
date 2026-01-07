#!/bin/bash

## Usage ##
# Example: 
#   sudo -E env "PATH=$PATH" run_benchmark.sh -p black -i 17 -m gpt5
#   sudo -E env "PATH=$PATH" run_benchmark.sh -p pandas -i 49 -m qwen

# Read benchmark project_name and bug ID
while getopts "p:i:m:" opt; do
  case $opt in
    p) project=${OPTARG};;
    i) bug_id=${OPTARG};;
    m) llm_model=${OPTARG};;
    \?)
      echo "Usage: $0 -p <project> -i <bug_id> -m <llm_model>"
      exit 1
      ;;
  esac
done

# Check both arguments provided
if [[ -z "$project" || -z "$bug_id" ]]; then
  echo "Error: Both -p <project> and -i <bug_id> are required."
  echo "Usage: $0 -p <project> -i <bug_id>"
  exit 1
fi

echo "   Starting Benchmark Test..."
echo "   Project: $project (Bug ID: $bug_id)"

# Activate Conda environment
default_conda_path=$HOME/anaconda3
conda_path="${CONDA_PATH:-$default_conda_path}"
source "$conda_path/etc/profile.d/conda.sh"

if conda info --envs | grep -q "${project}_${bug_id}"; then
  conda activate "${project}_${bug_id}"
else
  echo "Conda environment '${project}_${bug_id}' not found."
  exit 1
fi

# Get project DIR
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # ->  /axolotl(root)/scripts
project_root="$(cd "$script_dir/.." && pwd)"             # ->  /axolotl(root)
project_dir="$project_root/benchmarks/$project/$bug_id/buggy/$project"   # -> /axolotl(root)/benchmarks/<project>/<bug_id>/buggy/<project>
result_dir="$project_root/results/$project/$bug_id"    # -> /axolotl(root)/results/<project>/<bug_id>
test_command_path="$project_dir/bugsinpy_run_test.sh"                    # -> /axolotl(root)/benchmarks/<project>/<bug_id>/buggy/<project>/bugsinpy_run_test.sh

if [[ ! -f "$test_command_path" ]]; then
  echo "Test command file not found: $test_command_path"
  exit 1
fi

# Get test command from bugsinpy_run_test.sh
module=""
commands=()

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^# ]] && continue

  raw_args=""
  if [[ "$line" == *"pytest"* ]]; then
    module="pytest"
    raw_args="${line#*pytest}"
  elif [[ "$line" == *"unittest"* ]]; then
    module="unittest"
    raw_args="${line#*unittest}"
  fi

  if [[ -n "$raw_args" ]]; then
    read -ra tokens <<< "$raw_args"
    for token in "${tokens[@]}"; do
      if [[ "$token" != -* && -n "$token" ]]; then
        commands+=("$token")
      fi
    done
  fi

done < "$test_command_path"

if [[ -z "$module" ]]; then
  echo "No test command found in $test_command_path"
  exit 1
fi

# module : unittest or pytest
# commands : test command each buggy project

echo "Running Axolotl..."
### Run test on the axolotl framework
if [[ "$module" == "pytest" ]]; then
    sudo -E env "PATH=$PATH" "PYTHONPATH=$PYTHONPATH:$project_dir" python3 -m axolotl --wdir "$result_dir" --llm_model "$llm_model" --source "$project_dir" -m pytest -q -s "${commands[@]}"
elif [[ "$module" == "unittest" ]]; then
    sudo -E env "PATH=$PATH" "PYTHONPATH=$PYTHONPATH:$project_dir" python3 -m axolotl --wdir "$result_dir" --llm_model "$llm_model" --source "$project_dir" -m unittest -q "${commands[@]}"
else
  echo "Unsupported test module: $module"
  exit 1
fi

# checkpoints* 형태 dir cleanup, cleaner.py 이용
python3 "$script_dir/checkpoint_cleaner.py" "$result_dir/$llm_model/"checkpoints*

# Deactivate after tests
conda deactivate
echo "✅ Test Finished."