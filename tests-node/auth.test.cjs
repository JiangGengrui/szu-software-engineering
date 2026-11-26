'use strict';
// 账号与权限：小程序登录态状态机用例（AC-02、AC-11、AC-17、AC-18、AC-19、AC-20）
// 运行：npm test（会先执行 npm run build:mini，本文件读取编译后的 miniprogram/core/auth.js）

const test = require('node:test');
const assert = require('node:assert/strict');

const { AuthManager, validAuth } = require('../miniprogram/core/auth.js');
const { ApiError } = require('../miniprogram/core/transport.js');

const NOW = Date.parse('2026-11-26T08:00:00Z');
const NOW_FN = () => NOW;
const EXPIRES = '2026-12-03T08:00:00Z';

const user = (overrides = {}) => ({ id: 1, username: 'student_a', role: 'user', ...overrides });
const record = (overrides = {}) => ({ user: user(), token: 'signed-token', expires_at: EXPIRES, ...overrides });

function memoryStorage(initial) {
  let value = initial;
  return {
    get: () => value,
    set: next => { value = next; },
    remove: () => { value = undefined; },
    peek: () => value
  };
}

// --- validAuth：结构校验 ---------------------------------------------------

test('validAuth 接受结构完整的普通用户凭据', () => {
  assert.equal(validAuth(record()), true);
});

test('validAuth 拒绝非普通用户角色', () => {
  assert.equal(validAuth(record({ user: user({ role: 'admin' }) })), false);
});

test('validAuth 拒绝空 token 与非数字 id', () => {
  assert.equal(validAuth(record({ token: '' })), false);
  assert.equal(validAuth(record({ user: user({ id: '1' }) })), false);
  assert.equal(validAuth(record({ user: user({ id: 0 }) })), false);
});

test('validAuth 拒绝不可解析的 expires_at', () => {
  assert.equal(validAuth(record({ expires_at: 'not-a-date' })), false);
  assert.equal(validAuth(record({ expires_at: undefined })), false);
  assert.equal(validAuth(null), false);
  assert.equal(validAuth('string'), false);
});

// --- accept / user / token -------------------------------------------------

test('accept 落盘并立即使 user() 与 token() 可用（AC-02）', () => {
  const storage = memoryStorage(undefined);
  const manager = new AuthManager(storage, () => Promise.resolve(user()), NOW_FN);

  manager.accept(record());

  assert.deepEqual(manager.user(), user());
  assert.equal(manager.token(), 'signed-token');
  assert.deepEqual(storage.peek(), record());
});

test('accept 拒绝已过期的凭据并清空本地存储（AC-10）', () => {
  const storage = memoryStorage(undefined);
  const manager = new AuthManager(storage, () => Promise.resolve(user()), NOW_FN);

  assert.throws(() => manager.accept(record({ expires_at: '2026-11-25T08:00:00Z' })), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 403);
    assert.equal(error.code, 1003);
    return true;
  });
  assert.equal(manager.user(), null);
  assert.equal(storage.peek(), undefined);
});

test('accept 拒绝管理员身份，避免小程序侧提权（AC-17）', () => {
  const manager = new AuthManager(memoryStorage(undefined), () => Promise.resolve(user()), NOW_FN);

  assert.throws(() => manager.accept(record({ user: user({ role: 'admin' }) })), ApiError);
  assert.equal(manager.token(), undefined);
});

test('本地存有凭据但未经服务端确认时按游客处理（AC-11）', () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.resolve(user()), NOW_FN);

  assert.equal(manager.user(), null);
  assert.equal(manager.token(), undefined);
});

// --- confirm ---------------------------------------------------------------

test('confirm 成功后以服务端用户覆盖本地记录并置为已确认（AC-11）', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.resolve(user({ username: 'renamed' })), NOW_FN);

  const confirmed = await manager.confirm();

  assert.deepEqual(confirmed, user({ username: 'renamed' }));
  assert.equal(manager.token(), 'signed-token');
  assert.equal(storage.peek().user.username, 'renamed');
});

test('confirm 遇到 401 时清态并返回 null（AC-17/AC-19）', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.reject(new ApiError(401, 1002, '请重新登录')), NOW_FN);

  assert.equal(await manager.confirm(), null);
  assert.equal(manager.user(), null);
  assert.equal(storage.peek(), undefined);
});

test('confirm 遇到 403 时同样清态', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.reject(new ApiError(403, 1003, '无权限')), NOW_FN);

  assert.equal(await manager.confirm(), null);
  assert.equal(storage.peek(), undefined);
});

test('confirm 遇到网络错误时向上抛出，不误清登录态', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.reject(new ApiError(0, 0, '网络连接失败', true)), NOW_FN);

  await assert.rejects(() => manager.confirm(), ApiError);
  assert.equal(storage.peek().token, 'signed-token');
});

test('confirm 在等待响应期间被 clear 后不复活登录态（代次防护）', async () => {
  const storage = memoryStorage(record());
  let release;
  const manager = new AuthManager(storage, () => new Promise(resolve => { release = resolve; }), NOW_FN);

  const pending = manager.confirm();
  manager.clear();
  release(user());

  assert.equal(await pending, null);
  assert.equal(manager.user(), null);
  assert.equal(storage.peek(), undefined);
});

test('confirm 对已过期的本地记录不发请求，直接清态', async () => {
  const storage = memoryStorage(record({ expires_at: '2026-11-25T08:00:00Z' }));
  let called = false;
  const manager = new AuthManager(storage, () => { called = true; return Promise.resolve(user()); }, NOW_FN);

  assert.equal(await manager.confirm(), null);
  assert.equal(called, false);
  assert.equal(storage.peek(), undefined);
});

test('confirm 后服务端返回的用户 id 与本地不符时清态', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.resolve(user({ id: 99 })), NOW_FN);

  assert.equal(await manager.confirm(), null);
  assert.equal(manager.user(), null);
});

test('并发的 confirm 复用同一个请求', async () => {
  const storage = memoryStorage(record());
  let calls = 0;
  const manager = new AuthManager(storage, () => { calls += 1; return Promise.resolve(user()); }, NOW_FN);

  await Promise.all([manager.confirm(), manager.confirm()]);

  assert.equal(calls, 1);
});

// --- clear / 重新登录 ------------------------------------------------------

test('clear 后 token 失效，可重新 accept 新凭据（AC-18）', async () => {
  const storage = memoryStorage(record());
  const manager = new AuthManager(storage, () => Promise.resolve(user()), NOW_FN);
  manager.accept(record());

  manager.clear();
  assert.equal(manager.token(), undefined);

  manager.accept(record({ token: 'next-token' }));
  assert.equal(manager.token(), 'next-token');
});

test('ownsToken 只认当前记录，用于丢弃旧请求的 401', () => {
  const manager = new AuthManager(memoryStorage(undefined), () => Promise.resolve(user()), NOW_FN);
  manager.accept(record());

  assert.equal(manager.ownsToken('signed-token'), true);
  assert.equal(manager.ownsToken('other-token'), false);
});
