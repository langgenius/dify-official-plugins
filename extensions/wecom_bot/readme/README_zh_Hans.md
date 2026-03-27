

## 配置说明

#### 第一步，在企业微信中创建机器人应用

可以参考这篇[文章](https://cloud.tencent.com/document/product/1759/121473)

![1](./_assets/1.png)

进入到图示这一步以后，先把URL留空（下一步再填），先随机生成一个Token和Encoding-AESKey。


#### 第二步，在dify中进行插件配置
![2](./_assets/2.png)

在dify插件页面中找到`企业微信Bot`插件，添加一个配置，填入第一步得到的Token和Encoding-AESKey，并选择一个chat类型的dify应用。

![3](./_assets/3.png)

保存以后就能得到一个URL，再把它复制到第一步中企业微信的配置页面中，点击保存(若提示保存失败，可以再试一次)。

之后就可以在企业微信中和这个机器人愉快的聊天了:
![4](./_assets/4.jpg)