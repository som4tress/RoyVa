import {boundedDownload, MAX_BYTES, preparePrompt as expandVideos} from '../media-input/index.js';
export function attachment(message) {
  if (message.photo?.length) return {...message.photo.at(-1),mime:'image/jpeg',name:'photo.jpg'};
  if (message.video || message.video_note) return {...(message.video || message.video_note),mime:message.video?.mime_type || 'video/mp4',name:message.video?.file_name || 'video.mp4'};
  const doc=message.document;
  if (doc && /^(image|video)\//.test(doc.mime_type || '')) return {...doc,mime:doc.mime_type,name:doc.file_name || (/^video\//.test(doc.mime_type)?'video.mp4':'image.jpg')};
}
export async function telegramMedia(message,tg,token) {
  const media=attachment(message);if (!media) return [];
  if (media.file_size>MAX_BYTES || media.duration>600) throw Error('Photo/video limit: 20 MB; videos up to 10 minutes.');
  const file=await tg('getFile',{file_id:media.file_id});
  const data=await boundedDownload(await fetch(`https://api.telegram.org/file/bot${token}/${file.file_path}`,{signal:AbortSignal.timeout(60000)}));
  return [{uri:`data:${media.mime};base64,${data.toString('base64')}`,name:media.name}];
}
// Vanilla OpenCode does not load the media-input plugin, so videos are turned into sampled frames here, before the prompt is sent.
export async function withVideoFrames(files, text) {
  if (!files.some(f => /^data:video\//i.test(f.uri))) return {files, text};
  const event = {prompt: {files: [...files], text}, metadata: {}};
  await expandVideos(event);
  return {files: event.prompt.files, text: event.prompt.text};
}
