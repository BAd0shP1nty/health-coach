# Web chat (public demo). Works on Hugging Face Spaces (Docker SDK) and any container host. Listens on port 7860.
FROM python:3.12-slim
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
WORKDIR /home/user/app
COPY --chown=user requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt
# Pre-download the embedding model at build time so the first chat is fast.
RUN python -c "from chromadb.utils.embedding_functions import DefaultEmbeddingFunction as D; D()(['warm up'])"
COPY --chown=user . .
EXPOSE 7860
CMD ["streamlit", "run", "web_chat.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
