# LLM-Server
A server to run and use local and commercial LLM easier.

## Supported Models

* Local Models
  * Qwen 3
  * Qwen 3 Next
  * Llama-4 Scout
* Commercial Models
  * GPT-4.1-nano
  * GPT-5

### How to add more models
1. Add the model class in `llm_server/`. The model class should inherit from `BaseModel` in `model.py` and implement `__init__` and `request` methods.
2. Add the model to `__main__.py` to enable loading it from command line. Add it in `add_argument` function and in the model initialization section.

## Pre-requisites

* Python 3.10+
* Pytorch with CUDA support (if using GPU)

Anaconda or Miniconda is strongly recommended.

* Note: Qwen recommends Python 3.11+ for best performance.

Install dependencies:

```bash
pip install -r requirements.txt
```

:warning: Note: Pytorch are not included in requirements. Please install Pytorch separately according to your system and CUDA version. See https://pytorch.org/get-started/locally/ for more details.