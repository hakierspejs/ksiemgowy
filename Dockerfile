FROM python:3.10
ADD ./requirements.txt .
RUN python -m pip install -r requirements.txt
ADD ./ksiemgowy ksiemgowy
ADD ./config.yaml /etc/ksiemgowy/config.yaml
ENTRYPOINT ["python", "-m", "ksiemgowy"]
