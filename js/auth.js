/*
 * Autenticação do protótipo.
 * A senha nunca é gravada. O que fica no navegador é o hash SHA-256
 * com sal por usuário, mais uma sessão sem segredo (nome, e-mail, perfil e token).
 */
(function (root) {
  "use strict";

  const SESSION_KEY = "crmer.session";
  const USERS_KEY = "crmer.users";
  const PERFIS = ["vendedora", "vendedor", "administrador"];

  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ]);

  function rotr(value, bits) {
    return (value >>> bits) | (value << (32 - bits));
  }

  function sha256Hex(message) {
    const bytes = new TextEncoder().encode(message);
    const bitLen = bytes.length * 8;
    const padded = new Uint8Array((((bytes.length + 9 + 63) >> 6) << 6));
    padded.set(bytes);
    padded[bytes.length] = 0x80;
    const view = new DataView(padded.buffer);
    view.setUint32(padded.length - 8, Math.floor(bitLen / 0x100000000));
    view.setUint32(padded.length - 4, bitLen >>> 0);

    let h0 = 0x6a09e667;
    let h1 = 0xbb67ae85;
    let h2 = 0x3c6ef372;
    let h3 = 0xa54ff53a;
    let h4 = 0x510e527f;
    let h5 = 0x9b05688c;
    let h6 = 0x1f83d9ab;
    let h7 = 0x5be0cd19;
    const schedule = new Uint32Array(64);

    for (let offset = 0; offset < padded.length; offset += 64) {
      for (let index = 0; index < 16; index += 1) {
        schedule[index] = view.getUint32(offset + index * 4);
      }
      for (let index = 16; index < 64; index += 1) {
        const s0 = rotr(schedule[index - 15], 7) ^ rotr(schedule[index - 15], 18) ^ (schedule[index - 15] >>> 3);
        const s1 = rotr(schedule[index - 2], 17) ^ rotr(schedule[index - 2], 19) ^ (schedule[index - 2] >>> 10);
        schedule[index] = (schedule[index - 16] + s0 + schedule[index - 7] + s1) >>> 0;
      }

      let a = h0;
      let b = h1;
      let c = h2;
      let d = h3;
      let e = h4;
      let f = h5;
      let g = h6;
      let h = h7;

      for (let index = 0; index < 64; index += 1) {
        const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const choose = (e & f) ^ (~e & g);
        const temp1 = (h + s1 + choose + K[index] + schedule[index]) >>> 0;
        const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const majority = (a & b) ^ (a & c) ^ (b & c);
        const temp2 = (s0 + majority) >>> 0;
        h = g;
        g = f;
        f = e;
        e = (d + temp1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) >>> 0;
      }

      h0 = (h0 + a) >>> 0;
      h1 = (h1 + b) >>> 0;
      h2 = (h2 + c) >>> 0;
      h3 = (h3 + d) >>> 0;
      h4 = (h4 + e) >>> 0;
      h5 = (h5 + f) >>> 0;
      h6 = (h6 + g) >>> 0;
      h7 = (h7 + h) >>> 0;
    }

    return [h0, h1, h2, h3, h4, h5, h6, h7].map((part) => part.toString(16).padStart(8, "0")).join("");
  }

  function hashPassword(salt, password) {
    return sha256Hex(`${salt}:${password}`);
  }

  function randomHex(bytes) {
    const buffer = new Uint8Array(bytes);
    root.crypto.getRandomValues(buffer);
    return Array.from(buffer, (value) => value.toString(16).padStart(2, "0")).join("");
  }

  function storageError(action) {
    const error = new Error(`Não foi possível ${action} neste navegador. Verifique se o armazenamento local está liberado.`);
    error.code = "storage";
    return error;
  }

  function readStoredUsers() {
    try {
      const raw = root.localStorage.getItem(USERS_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((user) => user && typeof user.email === "string" && typeof user.passwordHash === "string" && typeof user.salt === "string");
    } catch (error) {
      return [];
    }
  }

  function writeStoredUsers(users) {
    try {
      root.localStorage.setItem(USERS_KEY, JSON.stringify(users));
    } catch (error) {
      throw storageError("gravar a conta");
    }
  }

  function seedUsers() {
    const mock = root.CRMER_MOCK;
    if (!mock || !Array.isArray(mock.usuarios)) {
      throw new Error("CRMER: a base de usuários de teste não foi carregada.");
    }
    return mock.usuarios;
  }

  function allUsers() {
    return seedUsers().concat(readStoredUsers());
  }

  function sameIdentity(user, identificador) {
    const key = identificador.trim().toLowerCase();
    return user.email.toLowerCase() === key || String(user.usuario || "").toLowerCase() === key;
  }

  function findUser(identificador) {
    return allUsers().find((user) => sameIdentity(user, identificador)) || null;
  }

  function publicSession(user, token) {
    return {
      nome: user.nome,
      email: user.email,
      perfil: user.perfil,
      token
    };
  }

  function saveSession(session) {
    try {
      root.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch (error) {
      throw storageError("gravar a sessão");
    }
  }

  function readSession() {
    try {
      const raw = root.localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      const session = JSON.parse(raw);
      const valid = session
        && typeof session.nome === "string"
        && session.nome.trim()
        && typeof session.email === "string"
        && session.email.includes("@")
        && PERFIS.includes(session.perfil)
        && typeof session.token === "string"
        && /^[0-9a-f]{32}$/.test(session.token);
      if (!valid) {
        root.localStorage.removeItem(SESSION_KEY);
        return null;
      }
      return {
        nome: session.nome,
        email: session.email,
        perfil: session.perfil,
        token: session.token
      };
    } catch (error) {
      return null;
    }
  }

  function clearSession() {
    try {
      root.localStorage.removeItem(SESSION_KEY);
    } catch (error) {
      /* A tela de login segue mesmo se o navegador bloquear a limpeza. */
    }
  }

  function login(identificador, password) {
    const user = findUser(identificador);
    if (!user || hashPassword(user.salt, password) !== user.passwordHash) return null;
    const session = publicSession(user, randomHex(16));
    saveSession(session);
    return session;
  }

  function uniqueUsuario(base) {
    const cleaned = String(base || "usuario").toLowerCase().replace(/[^a-z0-9._-]/g, "") || "usuario";
    const taken = new Set(allUsers().map((user) => String(user.usuario || "").toLowerCase()));
    if (!taken.has(cleaned)) return cleaned;
    let suffix = 2;
    while (taken.has(`${cleaned}${suffix}`)) suffix += 1;
    return `${cleaned}${suffix}`;
  }

  function validarSenha(password) {
    const value = String(password || "");
    const faltas = [];
    if (value.length < 8) faltas.push("no mínimo 8 caracteres");
    if (!/[A-Z]/.test(value)) faltas.push("uma letra maiúscula");
    if (!/[0-9]/.test(value)) faltas.push("um número");
    if (!/[!@#$%^&*(),.?":{}|<>_\-]/.test(value)) faltas.push("um caractere especial");
    return faltas;
  }

  function register(input) {
    const nome = String(input.nome || "").trim();
    const email = String(input.email || "").trim().toLowerCase();
    const password = String(input.password || "");
    const perfil = PERFIS.includes(input.perfil) ? input.perfil : "vendedora";
    const faltas = validarSenha(password);
    if (faltas.length) {
      const error = new Error(`A senha precisa de ${faltas.join(", ")}.`);
      error.code = "weak-password";
      throw error;
    }
    if (findUser(email)) {
      const error = new Error("Já existe uma conta com esse e-mail.");
      error.code = "duplicate";
      throw error;
    }
    const salt = randomHex(16);
    const record = {
      nome,
      email,
      usuario: uniqueUsuario(email.split("@")[0]),
      perfil,
      salt,
      passwordHash: hashPassword(salt, password)
    };
    const users = readStoredUsers();
    users.push(record);
    writeStoredUsers(users);
    const session = publicSession(record, randomHex(16));
    saveSession(session);
    return session;
  }

  root.CRMER_AUTH = {
    hashPassword,
    login,
    register,
    validarSenha,
    readSession,
    clearSession,
    perfis: PERFIS
  };
})(window);
