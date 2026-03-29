document.getElementById('subtitle-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const videoFile = document.getElementById('video-file').files[0];
  if (!videoFile) return alert('Please select a video file');

  // TO DO: Integrate with BasedSubtitles API/CLI
  // For example, using fetch to send the file to an API
  const formData = new FormData();
  formData.append('video', videoFile);

  try {
    const response = await fetch('/api/generate-subtitles', {
      method: 'POST',
      body: formData,
    });
    const subtitles = await response.text();
    document.getElementById('output').innerText = subtitles;
  } catch (error) {
    console.error(error);
    alert('Error generating subtitles');
  }
});
