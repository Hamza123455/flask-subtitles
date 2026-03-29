import { NextApiRequest, NextApiResponse } from 'next';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).send('Method not allowed');
  }

  const videoFile = req.body.video;
  // TO DO: Process the video file using BasedSubtitles code
  // For now, just return a success message
  res.status(200).send('Subtitles generated!');
}
