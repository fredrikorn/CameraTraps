WIP readme
This repository contains the code used in my thesis, where I experimented with different computer vision models on camera trap footage. 

I have used code from multiple other repositories and they have excellent documentation that you should check out to find more good explanations on how the different tools work.

# Setting up MegaDetector and recommendations for ECN
One goal with this project was to get a way to automate image processing/sorting for camera-trap images from the [ECN Cairngorms](https://eu-interact.org/field-sites/ecn-cairngorms/). My study ended up concluding that a 
For ECN's use of this repository, the best choice is to use Microsoft's MegaDetector, with a slight tweak to sort out dogs. This repo contains code that sorts out the images into the output folders "Animal", "Empty", "Human" and "Maybe", as well as recording the info in excel spreadsheets. However, the spreadsheet output is based on ECN's image namin convention, XX YYYYMMDD hhmmss.*, where xx is a camera abbreviation. If you don't have the same convention, the spreadsheet won't be useful.  

For ECN to get this output
1. Download [Anaconda](https://www.anaconda.com/products/individual) and [git](https://git-scm.com/downloads)
2. Open an **Anaconda prompt** and type the following commands:
    ```
    mkdir c:\git
    cd c:\git
    git clone https://github.com/fredrikorn/CameraTraps.git
    git clone https://github.com/Microsoft/ai4eutils
    ```
    These two repos are needed to use MegaDetector, but they also contain other useful tools, described the [CameraTraps-folder](/CameraTraps).
    
3. Download the [MegaDetector model file](https://lilablobssc.blob.core.windows.net/models/camera_traps/megadetector/md_v4.1.0/md_v4.1.0.pb) and put it in the folder. Cicking the link will download version 4.1.0, which I used, but you could also check for updated versions.
4. Create an **Anaconda environment** named *cameratraps-detector* by typing:
    ```
    conda env create --file environment-detector.yml
    ```
    This environment will contain the packages needed. Here, ordinarey tensorflow is used, but if you have a CUDA-compatible gpu on your computer you will probably want to change to the gpu-version.
    
5. Activate the environment by typing 'conda activate cameratraps-detector'
6. Type `run.cmd`. This will execute multiple commands and each could be run separately as well.

Done! Sorted images and excel spreadsheets will be in the output-folder.
