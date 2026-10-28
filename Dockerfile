FROM python:3.15
RUN apt-get update && apt-get install -y dumb-init && rm -rf /var/lib/apt /var/cache/apt
ADD ./requirements.txt .
RUN python -m pip install -r requirements.txt
ADD ./ksiemgowy ksiemgowy
ADD ./config.yaml /etc/ksiemgowy/config.yaml
ENTRYPOINT ["dumb-init", "python", "-m", "ksiemgowy"]
