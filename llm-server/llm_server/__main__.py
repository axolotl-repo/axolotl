import time
import flask
import os
import argparse
import logging
from huggingface_hub import login
from .model import app
from .llama import Llama4ScoutModel
from .qwen import Qwen3NextModel, Qwen3Model
from .gpt import GPT5Model, GPT4NanoModel

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM Server")
    parser.add_argument('model', type=str, choices=['llama-4-scout', 'qwen-3-next','qwen-3','gpt-5','gpt-4-nano'],
                        help='The model to serve.')
    parser.add_argument('-j', '--tensor-parallel-size', type=int, default=1,
                        help='Tensor parallel size for model loading.')
    parser.add_argument('--gpu-id', nargs='+', type=int, default=None,
                        help='List of GPU IDs to use for model loading.')
    parser.add_argument('--hf-token', type=str, default=None,
                        help='Hugging Face token for private model access.')
    parser.add_argument('-p', '--port', type=int, default=5000,
                        help='Port to run the server on.')
    parser.add_argument('--log-debug', action='store_true',
                        help='Enable debug level logging.')
    parser.add_argument('--max-tokens', type=int, default=8192,
                        help='Max length of tokens for model (prompt + response). Defualt: 8192')
    args = parser.parse_args()
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG if args.log_debug else logging.INFO)

    if args.gpu_id is not None:
        logger.info(f"Using GPUs: {args.gpu_id}")
        os.environ['CUDA_VISIBLE_DEVICES'] = ','.join(map(str, args.gpu_id))
    os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID' # Ensure consistent GPU ordering
    if args.hf_token is not None:
        logger.info("Logging in to Hugging Face Hub")
        login(token=args.hf_token)

    # Init model
    logger.info(f"Loading model: {args.model}")
    if args.model == 'llama-4-scout':
        model = Llama4ScoutModel(tensor_parallel_size=args.tensor_parallel_size, max_model_len=args.max_tokens)
    elif args.model == 'qwen-3-next':
        model = Qwen3NextModel(tensor_parallel_size=args.tensor_parallel_size, max_model_len=args.max_tokens)
    elif args.model == 'qwen-3':
        model = Qwen3Model(tensor_parallel_size=args.tensor_parallel_size, max_model_len=args.max_tokens)
    elif args.model == 'gpt-5':
        model = GPT5Model()
    elif args.model == 'gpt-4-nano':
        model = GPT4NanoModel()
    else:
        raise ValueError(f"Unsupported model: {args.model}")
    
    @app.route('/request', methods=['POST'])
    def handle_request():
        logger.debug("Received request")
        data:dict = flask.request.json
        system_msg = data['system_msg']
        prompt = data['prompt']
        start_time = time.time()
        response = model.request(system_msg, prompt)
        logger.info(f"Request processed in {time.time() - start_time:.2f} seconds")
        return flask.jsonify({'response': response})

    logger.info(f"Starting server on port {args.port}")
    app.run(host='127.0.0.1', port=args.port)