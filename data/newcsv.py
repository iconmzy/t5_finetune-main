import csv

input_file = 'input.csv'
output_file = 'output.csv'

# 读取 ISO-8859-1 编码的 CSV 文件
with open(input_file, 'r', encoding='iso-8859-1') as f:
    reader = csv.reader(f)
    data = list(reader)

# 将数据以 UTF-8 编码写入新的 CSV 文件
with open(output_file, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(data)

print("CSV 文件已转换为 UTF-8 编码并保存为 output.csv。")
