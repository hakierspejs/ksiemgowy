FROM python:3.7
ADD ./requirements-ksiemgowyd.txt .
RUN python -m pip install -r requirements-ksiemgowyd.txt
ADD ./ksiemgowy ksiemgowy
ADD ./config.yaml /etc/ksiemgowy/config.yaml
ENTRYPOINT ["python", "-m", "ksiemgowy"]
