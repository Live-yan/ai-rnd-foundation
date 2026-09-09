# Development workspace image. Pin a verified digest in your deployment.
FROM codercom/example-base:ubuntu
USER root
COPY import_source.py /opt/rnd/import_source.py
RUN chmod 0555 /opt/rnd/import_source.py
USER coder
