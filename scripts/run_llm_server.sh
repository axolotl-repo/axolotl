#!/bin/bash

# Usage (Default): ./run_llm_server.sh --api_key YOUR_OPENAI_KEY
# Usage (Advanced): ./run_llm_server.sh --hf_token YOUR_HF_TOKEN --model llama-4-scout -j 4 --gpu-id 0 1 2 3
# usage model: ['llama-4-scout', 'qwen-3-next','qwen-3','gpt-5','gpt-4-nano']

export PYTHONNOUSERSITE=1

# default setting
MODEL="gpt-5"
PORT=5000
OPENAI_KEY=""
HF_TOKEN=""
EXTRA_ARGS=() 

## parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --api_key) OPENAI_KEY="$2"; shift 2 ;;
        --hf_token) HF_TOKEN="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

## path
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
llm_server_dir=$(realpath "$script_dir/../llm-server")


### Create llm_server conda environment
default_conda_path=$HOME/anaconda3
conda_path="${CONDA_PATH:-$default_conda_path}"
source $conda_path/etc/profile.d/conda.sh

conda_env_name="llm_server"
if ! conda activate $conda_env_name; then
    echo "Creating conda environment $conda_env_name..."
    conda create -n $conda_env_name -y python=3.10
    conda activate $conda_env_name
    
    echo "Notice: Please ensure PyTorch is installed manually for your CUDA version."
    pip install -r "$llm_server_dir/requirements.txt"
fi

### run llm_server
cd $llm_server_dir/

# Run GPT models(DEFAULT)
if [[ "$MODEL" == gpt-* ]]; then
    if [ -n "$OPENAI_API_KEY" ]; then
        echo "Using OPENAI_API_KEY from environment variables."

    elif [ -n "$OPENAI_KEY" ]; then
        export OPENAI_API_KEY="$OPENAI_KEY"
        echo "Using API key provided via --api_key argument."
    
    else
        echo "Error: GPT models require OPENAI_API_KEY environment variable or --api_key argument."
        exit 1
    fi
    echo "Starting GPT server: $MODEL (Port: $PORT)"
    python -m llm_server "$MODEL" --port "$PORT" "${EXTRA_ARGS[@]}"
# Qwen models
elif [[ "$MODEL" == qwen-* ]]; then
    echo "Starting Qwen server: $MODEL (Port: $PORT)"
    python -m llm_server "$MODEL" --port "$PORT" "${EXTRA_ARGS[@]}"
# Llama models
else
    echo "Starting Open-source model server: $MODEL (Port: $PORT)"
    if [ -n "$HF_TOKEN" ]; then
        python -m llm_server "$MODEL" --port "$PORT" --hf-token "$HF_TOKEN" "${EXTRA_ARGS[@]}"
    else
        python -m llm_server "$MODEL" --port "$PORT" "${EXTRA_ARGS[@]}"
    fi
fi

echo "LLM server has been stopped."
conda deactivate
