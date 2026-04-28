const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'closetiq_super_secret_key_2024';

/**
 * Strict middleware — returns 401 if no valid token.
 */
function requireAuth(req, res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;

  if (!token) return res.status(401).json({ error: 'Authentication required' });

  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.user = payload;   // { id, name, email, username }
    next();
  } catch {
    return res.status(401).json({ error: 'Invalid or expired token' });
  }
}

/**
 * Optional middleware — attaches user if token present, does NOT block.
 */
function optionalAuth(req, _res, next) {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (token) {
    try {
      req.user = jwt.verify(token, JWT_SECRET);
    } catch { /* ignore invalid tokens */ }
  }
  next();
}

module.exports = { requireAuth, optionalAuth };
