import yaml
import csv
import math

CONFIG_PATH = "config.yaml"

with open(CONFIG_PATH) as f:
    cfg = yaml.safe_load(f)

csv_path = cfg["input_csv"]
col_x = cfg["columns"]["x"]
col_y = cfg["columns"]["y"]

xs = []
ys = []

with open(csv_path) as f:
    reader = csv.DictReader(f)
    for row in reader:
        xs.append(float(row[col_x]))
        ys.append(float(row[col_y]))

n = len(xs)

sum_x = 0.0
sum_y = 0.0
for i in range(n):
    sum_x = sum_x + xs[i]
    sum_y = sum_y + ys[i]

mean_x = sum_x / n
mean_y = sum_y / n

dx = 0.0
dy = 0.0
prod = 0.0
for i in range(n):
    a = xs[i] - mean_x
    b = ys[i] - mean_y
    dx = dx + a * a
    dy = dy + b * b
    prod = prod + a * b

denom = dx * dy
r = prod / denom

print("n =", n)
print("mean_x =", mean_x)
print("mean_y =", mean_y)
print("r =", r)
