import React from "react";
import {AbsoluteFill, Sequence} from "remotion";
import {Subtitle} from "./Subtitle";

type SubtitleItem = {
  id: number;
  start: number;
  end: number;
  lines: string[];
  fontSize: number;
};

const subtitles = require("../../public/subtitles.json") as SubtitleItem[];
const FPS = 30;

export const MainVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      {subtitles.map((subtitle) => {
        const from = Math.round(subtitle.start * FPS);
        const durationInFrames = Math.max(1, Math.round((subtitle.end - subtitle.start) * FPS));
        return (
          <Sequence key={subtitle.id} from={from} durationInFrames={durationInFrames}>
            <Subtitle lines={subtitle.lines} fontSize={subtitle.fontSize} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
