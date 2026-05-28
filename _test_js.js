
const { createApp } = Vue
createApp({
  data() {
    return {
      // Auth
      loggedIn: false,
      loginPassword: '',
      loginErr: '',
      loggingIn: false,
      token: localStorage.getItem('tietu_token') || '',

      // Tabs
      tab: 'tietu',

      // Tab 1: 贴图
      tietuUrl: '',
      tietuAccount: '',
      creatingTietu: false,
      tietuResult: null,

      // Tab 2: 二创
      rewriteUrl: '',
      parsing: false,
      parsedData: null,
      rewriteStyle: '更吸引人',
      rewriteStyles: [
        { key: '更吸引人', label: '🔥 更吸引人' },
        { key: '更专业', label: '📚 更专业' },
        { key: '更简洁', label: '✂️ 更简洁' },
        { key: '小红书风格', label: '📕 小红书风' },
      ],
      rewriting: false,
      rewrittenText: '',
      imagePrompt: '',
      generatingImage: false,
      generatedImage: '',
      rewriteAccount: '',
      publishingRewrite: false,
      rewriteDraftResult: null,

      // Tab 3: 写文章
      articleTopic: '',
      articleStyle: '通用',
      writingArticle: false,
      articleTitle: '',
      articleContent: '',
      articleAccount: '',
      creatingArticleDraft: false,
      articleDraftResult: null,

      // Modals
      showSettings: false,
      showAccounts: false,

      // Settings
      aiKey: '',
      testingKey: false,
      keyTestMsg: '',
      keyTestOk: false,
      oldPwd: '',
      newPwd: '',
      pwdMsg: '',

      // Accounts
      accounts: [],
      newAcc: { name: '', app_id: '', app_secret: '' },
      addingAcc: false,
      accMsg: '',

      // Toast
      toastMsg: '',
      toastType: 'info',
      toastTimer: null,
    }
  },
  mounted() {
    if (this.token) this.verifyAndLoad()
  },
  methods: {
    api() {
      return axios.create({
        baseURL: '/api',
        headers: this.token ? { Authorization: 'Bearer ' + this.token } : {},
        timeout: 180000
      })
    },

    async doLogin() {
      this.loginErr = ''
      if (!this.loginPassword) { this.loginErr = '请输入密码'; return }
      this.loggingIn = true
      try {
        const res = await axios.post('/api/auth/login', { password: this.loginPassword })
        this.token = res.data.token
        localStorage.setItem('tietu_token', this.token)
        this.loggedIn = true
        this.loginPassword = ''
        await this.loadData()
      } catch (e) {
        this.loginErr = e.response?.data?.message || '登录失败'
      }
      this.loggingIn = false
    },

    async verifyAndLoad() {
      try {
        const res = await axios.get('/api/auth/verify', {
          headers: { Authorization: 'Bearer ' + this.token }
        })
        this.loggedIn = true
        await this.loadData()
      } catch (e) {
        console.log('Token expired, need re-login:', e)
        localStorage.removeItem('tietu_token')
        this.token = ''
        this.loggedIn = false  // 关键：必须设为false，否则会显示空的主界面
      }
    },

    async loadData() {
      try {
        const [accRes, keyRes] = await Promise.all([
          this.api().get('/api/accounts'),
          this.api().get('/api/ai-key')
        ])
        this.accounts = accRes.data.accounts || []
      } catch (e) {
        console.error('loadData failed:', e)
        // 如果加载失败且token存在，可能是认证过期
        if (this.token) {
          localStorage.removeItem('tietu_token')
          this.token = ''
          this.loggedIn = false
        }
      }
    },

    toast(msg, type = 'info') {
      this.toastMsg = msg
      this.toastType = type
      clearTimeout(this.toastTimer)
      this.toastTimer = setTimeout(() => { this.toastMsg = '' }, 2500)
    },

    // ===== Tab 1: 贴图 =====
    async doCreateTietu() {
      if (!this.tietuAccount) { this.toast('请选择公众号', 'error'); return }
      if (!this.tietuUrl) { this.toast('请输入链接', 'error'); return }
      this.creatingTietu = true
      this.tietuResult = null
      try {
        const res = await this.api().post('/api/create-draft', { url: this.tietuUrl, account: this.tietuAccount })
        if (res.data.status === 'success') {
          this.tietuResult = res.data
          this.toast('✅ 贴图草稿创建成功！', 'success')
        } else {
          this.toast(res.data.message || '失败', 'error')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '创建失败', 'error')
      }
      this.creatingTietu = false
    },

    // ===== Tab 2: 二创 =====
    async doParse() {
      if (!this.rewriteUrl) { this.toast('请输入链接', 'error'); return }
      this.parsing = true
      this.parsedData = null
      try {
        const res = await this.api().post('/api/parse', { url: this.rewriteUrl })
        this.parsedData = res.data
        this.imagePrompt = '公众号封面图，' + (this.parsedData.title || '').substring(0, 20) + '，简约风格，16:9横屏'
        this.rewrittenText = ''
        this.generatedImage = ''
        this.toast(`解析成功: ${res.data.title?.substring(0,20)}...`, 'success')
      } catch (e) {
        this.toast(e.response?.data?.message || '解析失败，请检查链接', 'error')
      }
      this.parsing = false
    },

    async doRewrite() {
      if (!this.parsedData?.desc && !this.parsedData?.title) {
        this.toast('请先解析链接', 'error'); return
      }
      this.rewriting = true
      try {
        const res = await this.api().post('/api/ai/rewrite-text', {
          text: this.parsedData.desc || this.parsedData.title,
          title: this.parsedData.title,
          style: this.rewriteStyle
        })
        this.rewrittenText = res.data.rewritten
        this.toast('改写完成！', 'success')
      } catch (e) {
        const msg = e.response?.data?.message || '改写失败'
        if (msg.includes('请先配置')) this.showSettings = true
        this.toast(msg, 'error')
      }
      this.rewriting = false
    },

    async doGenImage() {
      if (!this.imagePrompt) { this.toast('请输入图片描述', 'error'); return }
      this.generatingImage = true
      try {
        const res = await this.api().post('/api/ai/generate-image', { prompt: this.imagePrompt })
        if (res.data.status === 'success') {
          this.generatedImage = res.data.image_url
          this.toast('图片生成成功！', 'success')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '生图失败', 'error')
      }
      this.generatingImage = false
    },

    async doPublishRewrite() {
      if (!this.rewriteAccount) { this.toast('请选择公众号', 'error'); return }
      if (!this.parsedData) { this.toast('请先解析链接', 'error'); return }
      this.publishingRewrite = true
      this.rewriteDraftResult = null
      try {
        const res = await this.api().post('/api/create-draft', {
          url: this.parsedData.source_url,
          account: this.rewriteAccount
        })
        if (res.data.status === 'success') {
          this.rewriteDraftResult = res.data
          this.toast('🚀 二创草稿创建成功！', 'success')
        } else {
          this.toast(res.data.message || '失败', 'error')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '创建失败', 'error')
      }
      this.publishingRewrite = false
    },

    // ===== Tab 3: 写文章 =====
    async doWriteArticle() {
      if (!this.articleTopic) { this.toast('请输入文章主题', 'error'); return }
      this.writingArticle = true
      this.articleContent = ''
      try {
        const res = await this.api().post('/api/ai/write-article', {
          topic: this.articleTopic, style: this.articleStyle
        })
        this.articleTitle = res.data.title
        this.articleContent = res.data.content_md
        this.toast('✅ 文章生成完毕！', 'success')
      } catch (e) {
        const msg = e.response?.data?.message || '写文章失败'
        if (msg.includes('请先配置')) this.showSettings = true
        this.toast(msg, 'error')
      }
      this.writingArticle = false
    },

    async doCreateArticleDraft() {
      if (!this.articleAccount) { this.toast('请选择发布公众号', 'error'); return }
      if (!this.articleContent) { this.toast('请先写文章', 'error'); return }
      this.creatingArticleDraft = true
      this.articleDraftResult = null
      try {
        const res = await this.api().post('/api/ai/create-article-draft', {
          account: this.articleAccount,
          title: this.articleTitle,
          content_md: this.articleContent,
          author: '',
          image_prompt: '公众号文章封面，' + this.articleTitle.substring(0, 20) + '，简约清新风格，16:9'
        })
        if (res.data.status === 'success') {
          this.articleDraftResult = res.data
          this.toast('🎉 文章草稿已创建！去公众号后台查看吧', 'success')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '创建失败: ' + (e.response?.data?.message || e.message), 'error')
      }
      this.creatingArticleDraft = false
    },

    // ===== Settings =====
    async saveAiKey() {
      if (!this.aiKey) { this.toast('请输入API Key', 'error'); return }
      try {
        await this.api().post('/api/ai-key', { api_key: this.aiKey })
        this.toast('API Key已保存', 'success')
      } catch (e) { this.toast('保存失败', 'error') }
    },

    async testAiKey() {
      if (!this.aiKey) { this.toast('请先输入API Key', 'error'); return }
      this.testingKey = true
      this.keyTestMsg = ''
      try {
        const res = await this.api().post('/api/ai/test-key', { api_key: this.aiKey })
        this.keyTestOk = res.data.success
        this.keyTestMsg = res.data.success ? '✅ 测通成功' : '❌ ' + (res.data.error || '测通失败')
      } catch { this.keyTestMsg = '❌ 网络错误'; this.keyTestOk = false }
      this.testingKey = false
    },

    async changePwd() {
      if (!this.oldPwd || !this.newPwd) { this.pwdMsg = '请填写完整'; return }
      if (this.newPwd.length < 4) { this.pwdMsg = '新密码至少4位'; return }
      try {
        await this.api().post('/api/auth/change-password', { old_password: this.oldPwd, new_password: this.newPwd })
        this.pwdMsg = '✅ 密码已修改'
        this.oldPwd = ''; this.newPwd = ''
      } catch (e) { this.pwdMsg = '❌ ' + (e.response?.data?.message || '失败') }
    },

    // ===== Accounts =====
    async addAccount() {
      const { name, app_id, app_secret } = this.newAcc
      if (!name || !app_id || !app_secret) { this.accMsg = '请填写完整'; return }
      this.addingAcc = true
      try {
        await this.api().post('/api/accounts/add', { name, app_id, app_secret })
        this.toast(`✅ "${name}" 添加成功`, 'success')
        this.newAcc = { name: '', app_id: '', app_secret: '' }
        this.accMsg = ''
        await this.loadData()
      } catch (e) { this.accMsg = '❌ ' + (e.response?.data?.message || '失败') }
      this.addingAcc = false
    },

    async deleteAccount(name) {
      if (!confirm(`确定删除 "${name}"？`)) return
      try {
        await this.api().post('/api/accounts/delete', { name })
        this.toast(`"${name}" 已删除`, 'info')
        await this.loadData()
      } catch (e) { this.toast('删除失败', 'error') }
    },

    // ===== Helpers =====
    renderMarkdown(md) {
      if (!md) return ''
      return md
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/!\[.*\]\((.+?)\)/g, '<br><img src="$1" style="max-width:100%;border-radius:8px;margin:8px 0"><br>')
        .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" style="color:#a78bfa">$1</a>')
        .split('\n\n').map(p => {
          if (/^<[hH]/.test(p)) return p
          if (p.trim().startsWith('- ') || p.trim().startsWith('1. ')) return '<p style="margin:4px 0">' + p.replace(/\n/g, '<br>') + '</p>'
          return '<p>' + p.replace(/\n/g, '<br>') + '</p>'
        }).join('')
    }
  }
}).mount('#app')

