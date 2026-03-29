const { generateSubtitles } = require('basedsubtitles');

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).send('Method not allowed');
  }

  // Parse the uploaded file (you might need 'formidable' or similar)
  // const videoFile = req.body.video; // This won't work as-is
  // For now, assume you handle file upload parsing

  try {
    const subtitles = await generateSubtitles(req.body.video); // Update this
    res.status(200).send(subtitles);
  } catch (err) {
    res.status(500).send('Error generating subtitles');
  }
}
