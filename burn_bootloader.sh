wget https://micropython.org/resources/firmware/esp32-20210902-v1.17.bin
esptool.py --chip esp32 --port COM3 erase_flash
esptool.py --chip esp32 --port COM3 write_flash -z 0x1000 .\esp32-20210902-v1.17.bin
