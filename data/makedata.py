import csv

# 输入文件路径
input_file = 'output.csv'
# 输出文件路径
train_source_file = 'train.source'
train_target_file = 'train.target'
val_source_file = 'val.source'
val_target_file = 'val.target'

# 计数器
count = 0

# 打开输入文件并读取数据
with open(input_file, 'r', encoding='utf-8') as file:
    reader = csv.reader(file)

    # 创建输出文件对象
    train_source = open(train_source_file, 'w', encoding='utf-8')
    train_target = open(train_target_file, 'w', encoding='utf-8')
    val_source = open(val_source_file, 'w', encoding='utf-8')
    val_target = open(val_target_file, 'w', encoding='utf-8')

    # 遍历输入文件的每一行
    for row in reader:
        # 获取新闻文本和摘要内容
        news_text = row[1]
        summary_text = row[0]
        # 去除新闻文本和摘要内容中的换行符
        news_text = news_text.replace('\n', '')
        summary_text = summary_text.replace('\n', '')
        # 判断计数器的值以确定写入的目标文件
        if count < 4000:
            train_source.write(news_text + '\n')
            train_target.write(summary_text + '\n')
        else:
            val_source.write(news_text + '\n')
            val_target.write(summary_text + '\n')

        count += 1

    # 关闭文件对象
    train_source.close()
    train_target.close()
    val_source.close()
    val_target.close()

print('文件处理完成。')
# 检查生成的文件行数
def count_lines(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    return len(lines)

# 检查train.source文件的行数
train_source_lines = count_lines(train_source_file)
print(f"train.source文件行数: {train_source_lines}")

# 检查train.target文件的行数
train_target_lines = count_lines(train_target_file)
print(f"train.target文件行数: {train_target_lines}")

# 检查val.source文件的行数
val_source_lines = count_lines(val_source_file)
print(f"val.source文件行数: {val_source_lines}")

# 检查val.target文件的行数
val_target_lines = count_lines(val_target_file)
print(f"val.target文件行数: {val_target_lines}")

