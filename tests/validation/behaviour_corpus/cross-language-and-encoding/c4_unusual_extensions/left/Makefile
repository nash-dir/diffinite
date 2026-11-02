# Build rules for the plotter firmware.
CC      ?= arm-none-eabi-gcc
OBJCOPY ?= arm-none-eabi-objcopy
CFLAGS  := -Os -Wall -Wextra -std=c99 -mcpu=cortex-m4 -mthumb -ffunction-sections
LDFLAGS := -Wl,--gc-sections -T linker/stm32f4.ld -nostartfiles
SRC_DIR := src
BUILD   := build

SOURCES := $(wildcard $(SRC_DIR)/*.c)
OBJECTS := $(patsubst $(SRC_DIR)/%.c,$(BUILD)/%.o,$(SOURCES))
DEPS    := $(OBJECTS:.o=.d)
TARGET  := $(BUILD)/plotter

.PHONY: all clean flash size test

all: $(TARGET).bin size

$(BUILD):
	mkdir -p $@

$(BUILD)/%.o: $(SRC_DIR)/%.c | $(BUILD)
	$(CC) $(CFLAGS) -MMD -MP -c $< -o $@

$(TARGET).elf: $(OBJECTS)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ -lm -o $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

size: $(TARGET).elf
	arm-none-eabi-size $<

flash: $(TARGET).bin
	st-flash --reset write $< 0x08000000

test:
	$(MAKE) -C tests CC=gcc
	./tests/run_all

clean:
	rm -rf $(BUILD)

-include $(DEPS)
