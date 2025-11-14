# wooldridge的Python项目详细描述

 

## wooldridge与python会面
> 来自的数据集介绍计量经济学：现代方法（第6版，j.m.wooldridge）

## 说明
一个python包，其中包含111个来自最著名的econometrics本科生教材的数据集。
## 如何使用

### 第一件事:
```from wooldridge import *```

加载名为<dataset>的数据集：
    
```dataWoo('<dataset>')```
    
它返回熊猫。

注意<dataset>是以字符串形式输入的。例如，将数据集mroz加载到df：
```df = dataWoo('mroz')```
显示数据集的描述（例如变量定义和源）：
```dataWoo('mroz', description=True)```
显示包中包含的111个数据集的列表
```dataWoo()```

    如何安装
```pip install wooldridge```
或
```git clone https://github.com/spring-haru/wooldridge.git pip install``` .
参考J.M.Wooldridge（2016）计量经济学导论：现代方法，Cengage Learning，第6版。