# Azgaar Fantasy Map Import: Blender Add-On

This Blender add-on imports a height map from [Azgaar's Fantasy Map Generator](https://github.com/Azgaar/Fantasy-Map-Generator).

## Installation

1. Download the file `io_azgaar.py` from this repository
2. Open Blender and navigate to `Edit > Preferences > Add-ons`
3. In the upper right-hand corner of the screen, open the arrow menu and select `Install from Disk...`
4. Select your downloaded file `io_azgaar.py`

## Usage

1. From the online Azgaar Fantasy Map Generator, export in "full" JSON format.
2. In Blender, from the top menu bar, select `File > Import > Azgaar Fantasy Map (.json)` and select your JSON file.
    - On the right-hand side of the file browser, there are options to set the default height of the ocean plane and vertical scale of the map.
3. To view biomes, set the viewport shading option to `Material Preview`
    - Biome colors can be edited by switching from `Object Mode` to `Vertex Paint`
4. All routes are imported, but are temporarilly hidden by default due to issues with discontinuous routes.

## Coming Soon

- Discontinuous route fixes
- Lakes above sea level
- Meandering river paths
- Tapered river widths
- Additional burg properties