import { NextApiRequest, NextApiResponse } from 'next';
import { generateSubtitles } from 'basedsubtitles';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).send('Method not allowed');
  }

  const videoFile = req.body.video;
  // TO DO: Parse the uploaded file
  const subtitles = await generateSubtitles(videoFile);
  res.status(200).send(subtitles);
}
