Page({
  data: {
    messages: [], // 对话内容
    inputValue: '', // 用户输入
    loading: false,
    conversation_id: '', // 会话ID
    user: 'wxuser_' + Math.floor(Math.random()*1000000)
  },
  onLoad() {
    // 页面加载时初始化
  },
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },
  sendMessage() {
    const query = this.data.inputValue.trim();
    if (!query) return;
    this.setData({ loading: true });
    const that = this;
    // 先把用户消息加入列表
    const userMsg = { role: 'user', content: query };
    const messages = that.data.messages.concat(userMsg);
    that.setData({ messages, inputValue: '' });
    wx.request({
      url: 'https://dify.刘竹.cn/v1/chat-messages',
      method: 'POST',
      header: {
        'Authorization': 'Bearer app-f92OaWtvzNipgzXNlFCng2HA',
        'Content-Type': 'application/json'
      },
      data: {
        query,
        response_mode: 'blocking',
        user: that.data.user,
        conversation_id: that.data.conversation_id || undefined
      },
      success(res) {
        if (res.data && res.data.answer) {
          // Dify 返回内容
          const aiMsg = { role: 'assistant', content: res.data.answer };
          messages.push(aiMsg);
          // 保存会话ID
          if (res.data.conversation_id) {
            that.setData({ conversation_id: res.data.conversation_id });
          }
          that.setData({ messages });
        } else {
          messages.push({ role: 'assistant', content: '未获取到有效回复' });
          that.setData({ messages });
        }
      },
      fail() {
        messages.push({ role: 'assistant', content: '请求失败，请稍后重试' });
        that.setData({ messages });
      },
      complete() {
        that.setData({ loading: false });
      }
    });
  }
});
