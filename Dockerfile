FROM apify/actor-python-playwright:3.12

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["python3", "-m", "src.main"]