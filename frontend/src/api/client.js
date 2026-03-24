import axios from 'axios'

const client = axios.create({
  baseURL: '/api',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

const PUBLIC_HASHES = ['#/onboarding', '#/login', '#/setup-password']

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      if (!PUBLIC_HASHES.some(r => window.location.hash.startsWith(r))) {
        window.location.hash = '#/onboarding'
      }
    }
    return Promise.reject(err)
  }
)

export default client
