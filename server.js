const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const axios = require('axios');
const FormData = require('form-data');
const { extractImagesFromPDF } = require('extract-pdf-images');

const app = express();
const uploadDirectory = './upload';
const outputImageDirectory = './images';

const imgbbApiKey = '93b5e89f0e0c87640ebe7ec6df835a55'; // 🔐 Replace with your API key

// CORS middleware - Add this BEFORE other middleware
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization');
    res.header('Access-Control-Allow-Credentials', 'true');

    if (req.method === 'OPTIONS') {
        res.sendStatus(200);
    } else {
        next();
    }
});

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Create directories if they don't exist
[uploadDirectory, outputImageDirectory].forEach(dir => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// Multer storage
const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, uploadDirectory),
    filename: (req, file, cb) => cb(null, file.originalname)
});
const upload = multer({ storage });


app.use(express.static(path.join(__dirname, 'public')));

// Optional: default route to index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// Serve static images with CORS headers
app.use('/images', (req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    next();
}, express.static(path.join(__dirname, 'images')));

// Upload route + image extraction
// Update the /upload route to handle page selection
app.post('/upload', upload.single('pdfFile'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({
                success: false,
                message: 'No PDF file uploaded.'
            });
        }

        const pdfPath = path.join(uploadDirectory, req.file.filename);
        console.log(`Processing PDF: ${pdfPath}`);

        // Get selected pages from request body (comma-separated string or array)
        const selectedPages = req.body.pages 
            ? req.body.pages.split(',').map(Number).filter(n => !isNaN(n))
            : null;

        const result = await extractImagesFromPDF(pdfPath, outputImageDirectory);
        
        // Filter results if specific pages are requested
        const filteredResult = selectedPages 
            ? result.filter(page => selectedPages.includes(page.pageNumber))
            : result;

        // Flatten the images while keeping page information
        const extractedImages = filteredResult.map(page => ({
            pageNumber: page.pageNumber,
            images: page.images.map(img => img.replace(/\\/g, '/'))
        }));

        console.log(`Extraction result:`, extractedImages);

        res.json({
            success: true,
            message: `Extracted images from ${filteredResult.length} pages`,
            pages: extractedImages,
            totalPages: result.length
        });
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({
            success: false,
            message: 'Error extracting images.',
            error: error.message,
            stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
        });
    }
});

app.post('/upload-to-imgbb', async (req, res) => {
    const { imagePath } = req.body;
    const fullPath = path.resolve(imagePath);

    console.log(`Attempting to upload: ${fullPath}`);

    if (!imagePath || !fs.existsSync(fullPath)) {
        console.log(`File not found: ${fullPath}`);
        return res.status(400).json({
            success: false,
            message: 'Invalid or missing image path.'
        });
    }

    try {
        const form = new FormData();
        form.append('image', fs.createReadStream(fullPath));

        const imgbbURL = `https://api.imgbb.com/1/upload?key=${imgbbApiKey}`;
        const response = await axios.post(imgbbURL, form, {
            headers: form.getHeaders()
        });

        const data = response.data.data;
        res.json({
            success: true,
            imageUrl: data.url,
            displayUrl: data.display_url,
            deleteUrl: data.delete_url
        });
    } catch (err) {
        console.error('ImgBB upload failed:', err.response?.data || err.message);
        res.status(500).json({
            success: false,
            message: 'Failed to upload to ImgBB.',
            error: err.message
        });
    }
});


// Update your /cleanup endpoint
app.post('/cleanup', async (req, res) => {
    const folders = [uploadDirectory, outputImageDirectory];

    try {
        let deletedCount = 0;
        folders.forEach(dir => {
            if (fs.existsSync(dir)) {
                fs.readdirSync(dir).forEach(fileOrFolder => {
                    const filePath = path.join(dir, fileOrFolder);
                    try {
                        if (fs.lstatSync(filePath).isDirectory()) {
                            fs.rmSync(filePath, { recursive: true, force: true });
                        } else {
                            fs.unlinkSync(filePath);
                        }
                        deletedCount++;
                    } catch (err) {
                        console.error(`Error deleting ${filePath}:`, err);
                    }
                });
                console.log(`Cleaned up directory: ${dir}`);
            }
        });

        res.json({  // Ensure this is always JSON
            success: true,
            message: 'Cleanup completed successfully',
            deletedCount: deletedCount
        });
    } catch (err) {
        console.error('Cleanup error:', err);
        res.status(500).json({  // Ensure error responses are JSON too
            success: false,
            message: 'Cleanup failed',
            error: err.message,
            deletedCount: 0
        });
    }
});

app.get('/existing-images', (req, res) => {
    const imageDir = path.join(__dirname, 'images');
    fs.readdir(imageDir, (err, files) => {
        if (err) {
            return res.status(500).json({ success: false, message: 'Unable to read images folder' });
        }
        const imagePaths = files
            .filter(file => /\.(jpg|jpeg|png|gif|bmp)$/i.test(file))
            .map(file => `images/${file}`);
        res.json({ success: true, images: imagePaths });
    });
});

// Add a test endpoint to check if server is working
app.get('/test', (req, res) => {
    res.json({
        message: 'Server is working!',
        timestamp: new Date().toISOString(),
        directories: {
            upload: fs.existsSync(uploadDirectory),
            images: fs.existsSync(outputImageDirectory)
        }
    });
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`Server running on http://localhost:${port}`);
});
