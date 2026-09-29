# Combine iterations: background arrows

Source: Figma file `M4IujdecP3N9GoOswgzDNl` (CG-Folio-WIP), section "12 iterate" (1:30377), Frame 198 (1:30378).

- `arrows.svg`: Vector 1:30380, the four chevrons, exported as-is from Figma. The 6% group opacity and the gradient (#4ECFEF, then #123456, then #FF5081 from left to right) are part of the file.
- `reference.png`: Figma render of Frame 198 at 1920x832.

## Geometry (px, relative to Frame 87 = 1:30379, 1920x832, which clips its content)

| Item | x | y | w | h |
|---|---|---|---|---|
| Vector 1:30380, Figma node box | -106.333 | -15.4287 | 2014.667 | 863.4285 |
| `arrows.svg` as exported (ink box) | -95.299 | -15.4287 | 2001.95 | 863.429 |
| Frame 197 (1:30383), the four screens | 150 | 10 | 1620 | 812 |

- Place `arrows.svg` at `left: -95.299px; top: -15.4287px` at its own size (2001.95x863.429). The export is 11.03px narrower than the node box, and that difference sits on the left. -95.299 is the offset between the same path point in the Vector export and in the Frame 87 export.
- Frame 87 clips the arrows to 0..1920 x 0..832.
- Relative to Frame 197's origin, the SVG sits at x -245.299, y -25.4287.
- The screens sit inside Frame 197 at x 0, 415, 830 and 1245 (375x812, 40px apart). In Frame 87 coordinates that is x 150, 565, 980 and 1395, all at y 10.
- Frame 87 also has two 1920x24 white fades, which are not in `arrows.svg`:
  - Rectangle 75 at y 0: white at the top, fading to transparent at the bottom.
  - Rectangle 76 at y 808: the same fade flipped, so it is transparent at the top and white at the bottom.

  In CSS: `linear-gradient(#fff, rgba(255,255,255,0))` and the reverse.
- Frame 87's background is white.

Check: `arrows.svg` rendered at this offset with the two fades, on white, matches `reference.png` everywhere outside the four screens. The largest channel difference is 7.
