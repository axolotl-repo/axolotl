sed -i 's|if pycompat.PY2:| |g' pysnooper/tracer.py
sed -i 's|    from io import open| |g' pysnooper/tracer.py
git stash push tests/test_pysnooper.py