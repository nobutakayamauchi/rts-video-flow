import React from "react";
import {Composition} from "remotion";
import {MainVideo} from "./MainVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="MainVideo"
      component={MainVideo}
      fps={30}
      width={1280}
      height={720}
      durationInFrames={60}
    />
  );
};
