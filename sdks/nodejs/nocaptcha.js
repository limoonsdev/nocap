/**
 * NoCaptcha Node.js client — zero dependencies (global fetch, Node 18+).
 *
 * const { NoCaptchaClient } = require('./nocaptcha');
 * const api = new NoCaptchaClient(); // http://127.0.0.1:7888
 * const res = await api.ocr('captcha.png', { kind: 'amazon' });
 * console.log(res.text);
 *
 * // hCaptcha token flow (see examples/hcaptcha-token-flow.js)
 * const { token } = await api.token('hcaptcha', 'xxx', 'https://example.com');
 */
'use strict';

const fs = require('fs');
const path = require('path');

class NoCaptchaError extends Error {}

function imageToB64(image) {
  if (Buffer.isBuffer(image)) return image.toString('base64');
  if (typeof image === 'string' && /^(https?:)?\/\//.test(image)) {
    throw new Error('pass URLs via imageUrl, not image');
  }
  if (typeof image === 'string' && fs.existsSync(image)) {
    return fs.readFileSync(image).toString('base64');
  }
  if (typeof image === 'string') return image; // assume base64
  throw new TypeError(`unsupported image input: ${typeof image}`);
}

class NoCaptchaClient {
  constructor(baseUrl = 'http://127.0.0.1:7888', timeoutMs = 120000) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.timeoutMs = timeoutMs;
  }

  async _postJson(path, payload) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const r = await fetch(this.baseUrl + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
      const body = await r.text();
      if (!r.ok) throw new NoCaptchaError(`HTTP ${r.status}: ${body.slice(0, 300)}`);
      return JSON.parse(body);
    } catch (e) {
      if (e instanceof NoCaptchaError) throw e;
      throw new NoCaptchaError(`request failed (${this.baseUrl}): ${e.message}`);
    } finally {
      clearTimeout(t);
    }
  }

  async _postFile(path, fields, files) {
    // files: { name: filepath }
    const form = new FormData();
    for (const [k, v] of Object.entries(fields)) {
      if (v !== undefined && v !== null) form.append(k, String(v));
    }
    for (const [k, fp] of Object.entries(files)) {
      const buf = fs.readFileSync(fp);
      form.append(k, new Blob([buf]), path.basename(fp));
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const r = await fetch(this.baseUrl + path, { method: 'POST', body: form, signal: ctrl.signal });
      const body = await r.text();
      if (!r.ok) throw new NoCaptchaError(`HTTP ${r.status}: ${body.slice(0, 300)}`);
      return JSON.parse(body);
    } catch (e) {
      if (e instanceof NoCaptchaError) throw e;
      throw new NoCaptchaError(`request failed (${this.baseUrl}): ${e.message}`);
    } finally {
      clearTimeout(t);
    }
  }

  async _get(path) {
    const r = await fetch(this.baseUrl + path);
    if (!r.ok) throw new NoCaptchaError(`HTTP ${r.status}`);
    return r.json();
  }

  /** Universal solver. `type` is required (see capabilities()). */
  solve({ type, image, imageUrl, image2, instruction, sitekey, url, langs = 'en', timeout = 90, ...data }) {
    const payload = { type, langs, timeout, data };
    if (image !== undefined) payload.image_b64 = imageToB64(image);
    if (imageUrl) payload.image_url = imageUrl;
    if (image2 !== undefined) payload.image_b64_2 = imageToB64(image2);
    if (instruction) payload.instruction = instruction;
    if (sitekey) payload.sitekey = sitekey;
    if (url) payload.url = url;
    return this._postJson('/v1/solve', payload);
  }

  /** Universal solver via raw file upload (no base64 needed). */
  solveFile({ type, file, file2, instruction, timeout = 90 }) {
    const files = { file };
    if (file2) files.file2 = file2;
    return this._postFile('/v1/solve/file', { type, instruction, timeout }, files);
  }

  ocr(image, { kind = 'auto', langs = 'en', imageUrl } = {}) {
    const payload = { kind, langs };
    if (image !== undefined) payload.image_b64 = imageToB64(image);
    if (imageUrl) payload.image_url = imageUrl;
    return this._postJson('/v1/solve/ocr', payload);
  }

  slider(bg, piece) {
    const payload = { bg_b64: imageToB64(bg) };
    if (piece !== undefined) payload.piece_b64 = imageToB64(piece);
    return this._postJson('/v1/solve/slider', payload);
  }

  click(image, instruction, { imageUrl } = {}) {
    const payload = { instruction };
    if (image !== undefined) payload.image_b64 = imageToB64(image);
    if (imageUrl) payload.image_url = imageUrl;
    return this._postJson('/v1/solve/click', payload);
  }

  /** Browser token flow: returns { token } to inject into the page. */
  token(type, sitekey, url, timeout = 120) {
    return this._postJson('/v1/solve', { type, sitekey, url, timeout, data: {} });
  }

  math({ text, image } = {}) {
    const payload = {};
    if (text) payload.text = text;
    if (image !== undefined) payload.image_b64 = imageToB64(image);
    return this._postJson('/v1/solve/math', payload);
  }

  health() { return this._get('/v1/health'); }
  capabilities() { return this._get('/v1/capabilities'); }
  stats() { return this._get('/v1/stats'); }
}

module.exports = { NoCaptchaClient, NoCaptchaError };
