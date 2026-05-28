
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

      // Tab 1: 璐村浘
      tietuUrl: '',
      tietuAccount: '',
      creatingTietu: false,
      tietuResult: null,

      // Tab 2: 浜屽垱
      rewriteUrl: '',
      parsing: false,
      parsedData: null,
      rewriteStyle: '鏇村惛寮曚汉',
      rewriteStyles: [
        { key: '鏇村惛寮曚汉', label: '馃敟 鏇村惛寮曚汉' },
        { key: '鏇翠笓涓?, label: '馃摎 鏇翠笓涓? },
        { key: '鏇寸畝娲?, label: '鉁傦笍 鏇寸畝娲? },
        { key: '灏忕孩涔﹂鏍?, label: '馃摃 灏忕孩涔﹂' },
      ],
      rewriting: false,
      rewrittenText: '',
      imagePrompt: '',
      generatingImage: false,
      generatedImage: '',
      rewriteAccount: '',
      publishingRewrite: false,
      rewriteDraftResult: null,

      // Tab 3: 鍐欐枃绔?      articleTopic: '',
      articleStyle: '閫氱敤',
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
      if (!this.loginPassword) { this.loginErr = '璇疯緭鍏ュ瘑鐮?; return }
      this.loggingIn = true
      try {
        const res = await axios.post('/api/auth/login', { password: this.loginPassword })
        this.token = res.data.token
        localStorage.setItem('tietu_token', this.token)
        this.loggedIn = true
        this.loginPassword = ''
        await this.loadData()
      } catch (e) {
        this.loginErr = e.response?.data?.message || '鐧诲綍澶辫触'
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
        this.loggedIn = false  // 鍏抽敭锛氬繀椤昏涓篺alse锛屽惁鍒欎細鏄剧ず绌虹殑涓荤晫闈?      }
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
        // 濡傛灉鍔犺浇澶辫触涓攖oken瀛樺湪锛屽彲鑳芥槸璁よ瘉杩囨湡
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

    // ===== Tab 1: 璐村浘 =====
    async doCreateTietu() {
      if (!this.tietuAccount) { this.toast('璇烽€夋嫨鍏紬鍙?, 'error'); return }
      if (!this.tietuUrl) { this.toast('璇疯緭鍏ラ摼鎺?, 'error'); return }
      this.creatingTietu = true
      this.tietuResult = null
      try {
        const res = await this.api().post('/api/create-draft', { url: this.tietuUrl, account: this.tietuAccount })
        if (res.data.status === 'success') {
          this.tietuResult = res.data
          this.toast('鉁?璐村浘鑽夌鍒涘缓鎴愬姛锛?, 'success')
        } else {
          this.toast(res.data.message || '澶辫触', 'error')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '鍒涘缓澶辫触', 'error')
      }
      this.creatingTietu = false
    },

    // ===== Tab 2: 浜屽垱 =====
    async doParse() {
      if (!this.rewriteUrl) { this.toast('璇疯緭鍏ラ摼鎺?, 'error'); return }
      this.parsing = true
      this.parsedData = null
      try {
        const res = await this.api().post('/api/parse', { url: this.rewriteUrl })
        this.parsedData = res.data
        this.imagePrompt = '鍏紬鍙峰皝闈㈠浘锛? + (this.parsedData.title || '').substring(0, 20) + '锛岀畝绾﹂鏍硷紝16:9妯睆'
        this.rewrittenText = ''
        this.generatedImage = ''
        this.toast(`瑙ｆ瀽鎴愬姛: ${res.data.title?.substring(0,20)}...`, 'success')
      } catch (e) {
        this.toast(e.response?.data?.message || '瑙ｆ瀽澶辫触锛岃妫€鏌ラ摼鎺?, 'error')
      }
      this.parsing = false
    },

    async doRewrite() {
      if (!this.parsedData?.desc && !this.parsedData?.title) {
        this.toast('璇峰厛瑙ｆ瀽閾炬帴', 'error'); return
      }
      this.rewriting = true
      try {
        const res = await this.api().post('/api/ai/rewrite-text', {
          text: this.parsedData.desc || this.parsedData.title,
          title: this.parsedData.title,
          style: this.rewriteStyle
        })
        this.rewrittenText = res.data.rewritten
        this.toast('鏀瑰啓瀹屾垚锛?, 'success')
      } catch (e) {
        const msg = e.response?.data?.message || '鏀瑰啓澶辫触'
        if (msg.includes('璇峰厛閰嶇疆')) this.showSettings = true
        this.toast(msg, 'error')
      }
      this.rewriting = false
    },

    async doGenImage() {
      if (!this.imagePrompt) { this.toast('璇疯緭鍏ュ浘鐗囨弿杩?, 'error'); return }
      this.generatingImage = true
      try {
        const res = await this.api().post('/api/ai/generate-image', { prompt: this.imagePrompt })
        if (res.data.status === 'success') {
          this.generatedImage = res.data.image_url
          this.toast('鍥剧墖鐢熸垚鎴愬姛锛?, 'success')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '鐢熷浘澶辫触', 'error')
      }
      this.generatingImage = false
    },

    async doPublishRewrite() {
      if (!this.rewriteAccount) { this.toast('璇烽€夋嫨鍏紬鍙?, 'error'); return }
      if (!this.parsedData) { this.toast('璇峰厛瑙ｆ瀽閾炬帴', 'error'); return }
      this.publishingRewrite = true
      this.rewriteDraftResult = null
      try {
        const res = await this.api().post('/api/create-draft', {
          url: this.parsedData.source_url,
          account: this.rewriteAccount
        })
        if (res.data.status === 'success') {
          this.rewriteDraftResult = res.data
          this.toast('馃殌 浜屽垱鑽夌鍒涘缓鎴愬姛锛?, 'success')
        } else {
          this.toast(res.data.message || '澶辫触', 'error')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '鍒涘缓澶辫触', 'error')
      }
      this.publishingRewrite = false
    },

    // ===== Tab 3: 鍐欐枃绔?=====
    async doWriteArticle() {
      if (!this.articleTopic) { this.toast('璇疯緭鍏ユ枃绔犱富棰?, 'error'); return }
      this.writingArticle = true
      this.articleContent = ''
      try {
        const res = await this.api().post('/api/ai/write-article', {
          topic: this.articleTopic, style: this.articleStyle
        })
        this.articleTitle = res.data.title
        this.articleContent = res.data.content_md
        this.toast('鉁?鏂囩珷鐢熸垚瀹屾瘯锛?, 'success')
      } catch (e) {
        const msg = e.response?.data?.message || '鍐欐枃绔犲け璐?
        if (msg.includes('璇峰厛閰嶇疆')) this.showSettings = true
        this.toast(msg, 'error')
      }
      this.writingArticle = false
    },

    async doCreateArticleDraft() {
      if (!this.articleAccount) { this.toast('璇烽€夋嫨鍙戝竷鍏紬鍙?, 'error'); return }
      if (!this.articleContent) { this.toast('璇峰厛鍐欐枃绔?, 'error'); return }
      this.creatingArticleDraft = true
      this.articleDraftResult = null
      try {
        const res = await this.api().post('/api/ai/create-article-draft', {
          account: this.articleAccount,
          title: this.articleTitle,
          content_md: this.articleContent,
          author: '',
          image_prompt: '鍏紬鍙锋枃绔犲皝闈紝' + this.articleTitle.substring(0, 20) + '锛岀畝绾︽竻鏂伴鏍硷紝16:9'
        })
        if (res.data.status === 'success') {
          this.articleDraftResult = res.data
          this.toast('馃帀 鏂囩珷鑽夌宸插垱寤猴紒鍘诲叕浼楀彿鍚庡彴鏌ョ湅鍚?, 'success')
        }
      } catch (e) {
        this.toast(e.response?.data?.message || '鍒涘缓澶辫触: ' + (e.response?.data?.message || e.message), 'error')
      }
      this.creatingArticleDraft = false
    },

    // ===== Settings =====
    async saveAiKey() {
      if (!this.aiKey) { this.toast('璇疯緭鍏PI Key', 'error'); return }
      try {
        await this.api().post('/api/ai-key', { api_key: this.aiKey })
        this.toast('API Key宸蹭繚瀛?, 'success')
      } catch (e) { this.toast('淇濆瓨澶辫触', 'error') }
    },

    async testAiKey() {
      if (!this.aiKey) { this.toast('璇峰厛杈撳叆API Key', 'error'); return }
      this.testingKey = true
      this.keyTestMsg = ''
      try {
        const res = await this.api().post('/api/ai/test-key', { api_key: this.aiKey })
        this.keyTestOk = res.data.success
        this.keyTestMsg = res.data.success ? '鉁?娴嬮€氭垚鍔? : '鉂?' + (res.data.error || '娴嬮€氬け璐?)
      } catch { this.keyTestMsg = '鉂?缃戠粶閿欒'; this.keyTestOk = false }
      this.testingKey = false
    },

    async changePwd() {
      if (!this.oldPwd || !this.newPwd) { this.pwdMsg = '璇峰～鍐欏畬鏁?; return }
      if (this.newPwd.length < 4) { this.pwdMsg = '鏂板瘑鐮佽嚦灏?浣?; return }
      try {
        await this.api().post('/api/auth/change-password', { old_password: this.oldPwd, new_password: this.newPwd })
        this.pwdMsg = '鉁?瀵嗙爜宸蹭慨鏀?
        this.oldPwd = ''; this.newPwd = ''
      } catch (e) { this.pwdMsg = '鉂?' + (e.response?.data?.message || '澶辫触') }
    },

    // ===== Accounts =====
    async addAccount() {
      const { name, app_id, app_secret } = this.newAcc
      if (!name || !app_id || !app_secret) { this.accMsg = '璇峰～鍐欏畬鏁?; return }
      this.addingAcc = true
      try {
        await this.api().post('/api/accounts/add', { name, app_id, app_secret })
        this.toast(`鉁?"${name}" 娣诲姞鎴愬姛`, 'success')
        this.newAcc = { name: '', app_id: '', app_secret: '' }
        this.accMsg = ''
        await this.loadData()
      } catch (e) { this.accMsg = '鉂?' + (e.response?.data?.message || '澶辫触') }
      this.addingAcc = false
    },

    async deleteAccount(name) {
      if (!confirm(`纭畾鍒犻櫎 "${name}"锛焋)) return
      try {
        await this.api().post('/api/accounts/delete', { name })
        this.toast(`"${name}" 宸插垹闄, 'info')
        await this.loadData()
      } catch (e) { this.toast('鍒犻櫎澶辫触', 'error') }
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

