# UGBS Service Navigator — API server, for a Hugging Face Docker Space.
#
# Uploaded by tools/deploy_backend.py, which places this file at the Space root.
# The GROQ_API_KEY and CORS_ORIGINS values are Space secrets, never baked in.

FROM python:3.12-slim

# Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# CPU-only torch first: the default wheel bundles CUDA and is several times larger.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user --index-url https://download.pytorch.org/whl/cpu torch==2.13.0 \
 && pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user . .

# Everything slow happens at build time, not when the first visitor arrives:
# download the embedding model, embed the passages, and seed the simulated
# semester so the dashboard has data from the first request.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')" \
 && python tools/build_index.py --from-chunks \
 && python tools/seed_enquiries.py --reset

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
