import os
import sys
import json
import shutil
import pandas as pd

from pandas import DataFrame

#### GLOBAL CONSTANTS, CHANGE IF YOU CHANGE FOLDER NAMES #####
IMG_FOLDER = "test_images"
MD_OUTPUT = "some_output_file.json"
OUTPUT_FOLDER = "output/"
TH = 0.8
##############################################################

def camera_name(cam):
    if cam == 'BR':
        return 'Bridge'
    elif cam == 'PA':
        return 'Path'
    elif cam == 'TL':
        return 'Treeline'
    elif cam == 'TR':
        return 'Track'
    elif cam == 'TS':
        return 'TSS'
    elif cam == 'ZZ':
        return 'Zigzag'
    elif cam == 'CP':
        return 'carpark'
    elif cam == 'ST':
        return 'stream'
    elif cam == 'SN':
        return 'SNH'
    else:
        print('Unknown camera: '+ cam )
        return cam


def main():
    folder = IMG_FOLDER
    pics = os.listdir(folder)
    try:
        json_data = json.load(open(MD_OUTPUT))

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]

        msg = "ERROR : {}, moreInfo : {}\t{}\t{}".format(
            e, exc_type, fname, exc_tb.tb_lineno)

        print(msg)
        return False, msg

    human_cameras = list()
    human_timestamps = list()
    human_number = list()
    dog_number = list()
    human_filenames = list()

    animal_cameras = list()
    animal_number = list()
    animal_timestamps = list()
    animal_filenames = list()
    
    # ADD TQDM BAR? 
    # Reads all detections in lists that will be saved as an excel-file
    for img in json_data["images"]:
        filename = (img["file"].split("/")[-1]).split("\\")[-1]
        cam = filename[0:2]
        Y = filename[-19:-15]
        M = filename[-15:-13]
        D = filename[-13:-11]
        h = filename[-10:-8]
        m = filename[-8:-6]
        s = filename[-6:-4]

        try:
            ts = pd.Timestamp(Y + '-' + M + '-'+ D + ' ' + h + ':' + m + ':' + s)
        except:
            print("Could not convert to timestamp for filename: "+filename)
        
        animals = 0
        humans = 0
        dogs = 0
        
        for det in img["detections"]:
            if det["conf"] >= TH:
                if det["category"] == '1':
                    animals +=1
                elif det["category"] == '2':
                    humans +=1
            else:
                break
        
        if animals > 0 and humans > 0:
            dogs = animals
            animals = 0
            
        elif animals > 0:
            animal_cameras.append(camera_name(cam)) 
            animal_number.append(animals)
            animal_timestamps.append(ts)
            animal_filenames.append(filename)
            
        if humans > 0:
            human_cameras.append( camera_name(cam) )
            human_timestamps.append(ts)
            human_number.append(humans)
            dog_number.append(dogs)
            human_filenames.append(filename)

    # Changes animal detections to dogs if there was a human detected on the same camera close in time
    i=0
    while i in range(len(animal_filenames)):
        dog = False
        for j in range(len(human_filenames)):
            if (animal_cameras[i] == human_cameras[j] and 
                abs((animal_timestamps[i]-human_timestamps[j]).total_seconds()) < 300): # Different timespan could be used
                
                dog = True
                human_cameras.append(animal_cameras.pop(i))
                human_timestamps.append(animal_timestamps.pop(i))
                human_number.append(0)
                dog_number.append(animal_number.pop(i))
                human_filenames.append(animal_filenames.pop(i))
                break
        
        if not dog:
            i+=1
    
    #region
    #### Saving detections in excel-sheets
    animal_df = DataFrame({'Timestamp': animal_timestamps, 'Camera': animal_cameras, 
                      'Number': animal_number})
    human_df = DataFrame({'Timestamp': human_timestamps, 'Camera': human_cameras, 
                        'Number': human_number, 'Dogs': dog_number})

    animal_df.to_excel(OUTPUT_FOLDER+'wildlife.xlsx', sheet_name='sheet1', index=False)
    human_df.to_excel(OUTPUT_FOLDER+'people.xlsx', sheet_name='sheet1', index=False)
    #endregion

if __name__ == '__main__':
    main()

