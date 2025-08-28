API 公平使用规则
在你开始使用 V2EX API 之前，请了解我们关于 API 公平使用方面的规则：

我们鼓励将 V2EX API 用于学术研究、手机应用及浏览器扩展
我们反对将 API 输出的结果用于填充你的商业或是个人网站的内容。如果你对于本条规则有疑问，可以到 V2EX 元节点讨论。我们对于 API 的一切有意义的用途持开放态度，只是不希望 V2EX 的数据被用在垃圾站和 content farm
V2EX 不会删除或是更改已经发布的 API 接口的 URI 及字段名
大部分 API 会带有每小时请求数量限制，但是因为大部分 API 请求是可以被 CDN 缓存的，所以可用请求数只会在第一次请求时从配额中减去
关于 API 使用的讨论，可以到以下 meta 节点：

http://www.v2ex.com/go/v2ex

API Rate Limit
默认情况下，每个 IP 每小时可以发起的 API 请求数被限制在 120 次。你可以在 API 返回结果的 HTTP 头部找到 Rate Limit 信息：

X-Rate-Limit-Limit: 120
X-Rate-Limit-Reset: 1409479200
X-Rate-Limit-Remaining: 116
对于能够被 CDN 缓存的 API 请求，只有第一次请求时，才会消耗 Rate Limit 配额。

最热主题
相当于首页右侧的 10 大每天的内容。

https://www.v2ex.com/api/topics/hot.json

Method: GET
Authentication: None
最新主题
相当于首页的“全部”这个 tab 下的最新内容。

https://www.v2ex.com/api/topics/latest.json

Method: GET
Authentication: None
节点信息
获得指定节点的名字，简介，URL 及头像图片的地址。

https://www.v2ex.com/api/nodes/show.json

Method: GET
Authentication: None
接受参数：

name: 节点名（V2EX 的节点名全是半角英文或者数字）
例如：

https://www.v2ex.com/api/nodes/show.json?name=python

用户主页
获得指定用户的自我介绍，及其登记的社交网站信息。

https://www.v2ex.com/api/members/show.json

Method: GET
Authentication: None
接受以下参数之一：

username: 用户名
id: 用户在 V2EX 的数字 ID
例如：

https://www.v2ex.com/api/members/show.json?username=Livid
https://www.v2ex.com/api/members/show.json?id=1