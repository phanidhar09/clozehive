const multer = require('multer');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const fs = require('fs');

const UPLOAD_DIR = process.env.UPLOAD_DIR
  ? path.resolve(__dirname, '../../', process.env.UPLOAD_DIR)
  : path.join(__dirname, '../../uploads');

// Ensure upload dir exists
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, UPLOAD_DIR),
  filename: (_req, file, cb) => {
    const ext = path.extname(file.originalname).toLowerCase();
    cb(null, `item_${uuidv4()}${ext}`);
  },
});

const fileFilter = (_req, file, cb) => {
  const allowed = ['.jpg', '.jpeg', '.png', '.webp', '.heic'];
  const ext = path.extname(file.originalname).toLowerCase();
  allowed.includes(ext) ? cb(null, true) : cb(new Error('Only image files are allowed'));
};

const upload = multer({
  storage,
  fileFilter,
  limits: { fileSize: parseInt(process.env.MAX_FILE_SIZE || '10485760') },
});

module.exports = upload;
