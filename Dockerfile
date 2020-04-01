FROM python:3.7
ADD ./requirements.txt .
RUN python -m pip install -r requirements.txt
ADD ./ksiemgowy ksiemgowy
ENTRYPOINT ["python", "-m", "ksiemgowy"]
