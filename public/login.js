(() => {
  const form = document.querySelector('#authForm');
  const email = document.querySelector('#email');
  const password = document.querySelector('#password');
  const submit = document.querySelector('#submitButton');
  const toggle = document.querySelector('#toggleMode');
  const title = document.querySelector('#authTitle');
  const copy = document.querySelector('#authCopy');
  const errorBox = document.querySelector('#authError');
  let mode = 'login';

  async function request(path, payload) {
    const response = await fetch(path, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }

  function renderMode() {
    const registering = mode === 'register';
    document.body.classList.toggle('mode-register', registering);
    title.textContent = registering ? 'Create your NeoGen account' : 'Welcome back';
    copy.textContent = registering ? 'Create a private local account for this NeoGen installation.' : 'Sign in to continue to your private NeoGen workspace.';
    submit.textContent = registering ? 'Create account' : 'Continue';
    toggle.textContent = registering ? 'Use an existing account' : 'Create an account';
    password.autocomplete = registering ? 'new-password' : 'current-password';
    errorBox.textContent = '';
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.textContent = '';
    const payload = { email: email.value.trim(), password: password.value };
    if (!payload.email || !payload.password) return void (errorBox.textContent = 'Enter your email and password.');
    submit.disabled = true;
    submit.textContent = mode === 'register' ? 'Creating account…' : 'Signing in…';
    try {
      await request(mode === 'register' ? '/api/auth/register' : '/api/auth/login', payload);
      location.replace('/');
    } catch (error) {
      errorBox.textContent = error.message;
    } finally {
      submit.disabled = false;
      renderMode();
    }
  });

  toggle.addEventListener('click', () => { mode = mode === 'login' ? 'register' : 'login'; renderMode(); });
  fetch('/api/auth/me', { credentials: 'same-origin' }).then((response) => { if (response.ok) location.replace('/'); }).catch(() => {});
  renderMode();
})();
