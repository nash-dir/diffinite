'use strict';
const { EventEmitter } = require('events');



function compilePattern(pattern) {

  const keys = [];
  const source = pattern
    .replace(/\/+$/, '')
    .replace(/:(\w+)(\?)?/g, (_, key, optional) => {

      keys.push({ name: key, optional: Boolean(optional) });
      return optional ? '(?:/([^/]+))?' : '/([^/]+)';
    })
    .replace(/\/\(\?:/g, '(?:');
  return { regex: new RegExp(`^${source || '/'}/?$`, 'i'), keys };
}



class Router extends EventEmitter {




  constructor(options = {}) {

    super();
    this.routes = [];
    this.middleware = [];
    this.caseSensitive = Boolean(options.caseSensitive);
    this.notFound = options.notFound || ((req, res) => res.status(404).send('Not Found'));
  }



  use(fn) {

    if (typeof fn !== 'function') {

      throw new TypeError('middleware must be a function');
    }
    this.middleware.push(fn);
    return this;
  }



  add(method, pattern, handler) {

    const { regex, keys } = compilePattern(pattern);
    this.routes.push({ method: method.toUpperCase(), pattern, regex, keys, handler });
    this.emit('route:added', method, pattern);
    return this;
  }



  get(pattern, handler) {

    return this.add('GET', pattern, handler);
  }



  post(pattern, handler) {

    return this.add('POST', pattern, handler);
  }



  match(method, path) {

    for (const route of this.routes) {

      if (route.method !== method && route.method !== 'ALL') {

        continue;
      }
      const m = route.regex.exec(path);
      if (!m) {

        continue;
      }
      const params = {};
      route.keys.forEach((key, i) => {

        const raw = m[i + 1];
        if (raw !== undefined) {

          params[key.name] = decodeURIComponent(raw);
        }
      });
      return { route, params };
    }
    return null;
  }



  async handle(req, res) {

    const started = Date.now();
    let index = 0;
    const next = async (err) => {

      if (err) {

        this.emit('error', err, req);
        res.status(500).send('Internal Server Error');
        return;
      }
      const mw = this.middleware[index++];
      if (mw) {

        await mw(req, res, next);
        return;
      }
      const found = this.match(req.method, req.path);
      if (!found) {

        this.notFound(req, res);
        return;
      }
      req.params = found.params;
      try {

        await found.route.handler(req, res);
      } catch (e) {

        await next(e);
      }
    };
    await next();
    this.emit('request:done', req.method, req.path, Date.now() - started);
  }



  list() {

    return this.routes.map((r) => `${r.method.padEnd(6)} ${r.pattern}`);
  }
}
module.exports = { Router, compilePattern };
