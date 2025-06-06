# 训练数据路径配置示例

在 `app_config.py` 中，您可以通过修改 `TRAINING_DATA_PATH` 来配置训练数据的路径。

## 配置方式

### 1. 相对路径（以 . 开头）
```python
# 项目根目录下的training/data文件夹
TRAINING_DATA_PATH = "./training/data"

# 项目根目录下的my_training_data文件夹
TRAINING_DATA_PATH = "./my_training_data"

# 项目根目录上级的data文件夹
TRAINING_DATA_PATH = "../data"

# 项目根目录上级的training_files文件夹
TRAINING_DATA_PATH = "../training_files"
```

### 2. 绝对路径

#### Linux/Mac 系统
```python
# Linux绝对路径
TRAINING_DATA_PATH = "/home/username/training_data"

# Mac绝对路径
TRAINING_DATA_PATH = "/Users/username/Documents/training_data"
```

#### Windows 系统
```python
# Windows绝对路径（使用正斜杠）
TRAINING_DATA_PATH = "C:/training_data"
TRAINING_DATA_PATH = "D:/Projects/my_training_data"

# Windows绝对路径（使用反斜杠，需要转义）
TRAINING_DATA_PATH = "C:\\training_data"
TRAINING_DATA_PATH = "D:\\Projects\\my_training_data"
```

### 3. 相对路径（不以 . 开头）
```python
# 相对于项目根目录
TRAINING_DATA_PATH = "training/data"      # 等同于 "./training/data"
TRAINING_DATA_PATH = "my_data"            # 等同于 "./my_data"
TRAINING_DATA_PATH = "data/training"      # 等同于 "./data/training"
```

## 使用示例

### 默认配置
```python
# 使用项目默认的训练数据目录
TRAINING_DATA_PATH = "./training/data"
```

### 自定义本地目录
```python
# 使用项目根目录下的自定义文件夹
TRAINING_DATA_PATH = "./my_training_files"
```

### 外部目录
```python
# Linux/Mac
TRAINING_DATA_PATH = "/home/user/Documents/sql_training_data"

# Windows
TRAINING_DATA_PATH = "D:/SQL_Training_Data"
```

## 命令行覆盖

即使在配置文件中设置了路径，您仍然可以通过命令行参数临时覆盖：

```bash
# 使用配置文件中的路径
python training/run_training.py

# 临时使用其他路径
python training/run_training.py --data_path "./custom_data"
python training/run_training.py --data_path "/absolute/path/to/data"
python training/run_training.py --data_path "C:/Windows/Path/To/Data"
```

## 路径验证

运行训练脚本时，会显示路径解析结果：
```
===== 训练数据路径配置 =====
配置文件中的路径: ./training/data
解析后的绝对路径: /full/path/to/project/training/data
==============================
```

这样您可以确认路径是否正确解析。 