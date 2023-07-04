import csv

def count_rows(filename):
    count = 0
    with open(filename, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            count += 1
    return count

train_source_file = 'trainsource.csv'
train_target_file = 'traintarget.csv'

train_source_count = count_rows(train_source_file)
train_target_count = count_rows(train_target_file)

print(f"trainsource.csv 行数: {train_source_count}")
print(f"traintarget.csv 行数: {train_target_count}")
