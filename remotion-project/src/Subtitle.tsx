import React from "react";
import {AbsoluteFill} from "remotion";
import {loadFont} from "@remotion/google-fonts/NotoSansJP";

const {fontFamily} = loadFont();

export const Subtitle: React.FC<{lines: string[]; fontSize: number}> = ({lines, fontSize}) => {
  return (
    <AbsoluteFill style={{justifyContent: "flex-end", alignItems: "center", bottom: 40}}>
      <div
        style={{
          fontFamily,
          color: "white",
          fontSize,
          textAlign: "center",
          textShadow: "0 2px 8px rgba(0,0,0,0.8)",
          whiteSpace: "pre-line",
          paddingBottom: 24,
        }}
      >
        {lines.join("\n")}
      </div>
    </AbsoluteFill>
  );
};
