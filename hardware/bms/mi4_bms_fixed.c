// SPDX-License-Identifier: GPL

/*
 * Qualcomm Battery Monitoring System driver
 *
 * Copyright (C) 2018 Craig Tatlor <ctatlor97@gmail.com>
 * Copyright (C) 2025 Zhiyuan Bai <Bzy080408@outlook.com>
 */

#include <linux/module.h>
#include <linux/fixp-arith.h>
#include <linux/platform_device.h>
#include <linux/power_supply.h>
#include <linux/slab.h>
#include <linux/bitops.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/regmap.h>
#include <linux/irq.h>
#include <linux/interrupt.h>
#include <linux/iio/consumer.h>
#include <linux/iio/iio.h>
#include <linux/unaligned.h>

#define REG_BMS_OCV_FOR_SOC_DATA0	0x90
#define REG_BMS_SHDW_CC_DATA0		0xA8
#define REG_BMS_CC_DATA_CTL		0x42
#define REG_BMS_CC_CLEAR_CTL		0x4

#define BMS_HOLD_OREG_DATA		BIT(0)
#define BMS_CLEAR_SHDW_CC		BIT(6)

#define BMS_CC_READING_RESOLUTION_N	542535
#define BMS_CC_READING_RESOLUTION_D	100000
#define BMS_CC_READING_TICKS		56
#define BMS_SLEEP_CLK_HZ		32764

#define SECONDS_PER_HOUR		3600
#define TEMPERATURE_COLS		5
#define MAX_CAPACITY_ROWS		50

/* lookup table for ocv -> capacity conversion */
struct bms_ocv_lut {
	int rows;
	s8 temp_legend[TEMPERATURE_COLS];
	u8 capacity_legend[MAX_CAPACITY_ROWS];
	u32 lut[MAX_CAPACITY_ROWS][TEMPERATURE_COLS];
};

/* lookup table for battery temperature -> fcc conversion */
struct bms_fcc_lut {
	s8 temp_legend[TEMPERATURE_COLS];
	u32 lut[TEMPERATURE_COLS];
};

struct bms_device_info {
	struct device *dev;
	struct power_supply *battery;
	struct power_supply_battery_info *info;
	struct regmap *regmap;
	struct bms_ocv_lut ocv_lut;
	struct power_supply_desc bat_desc;
	struct bms_fcc_lut fcc_lut;
	struct iio_channel *adc;
	struct mutex bms_output_lock;
	struct mutex sample_lock;
	u32 base_addr;

	int ocv_thr_irq;
	u32 ocv;
	u16 ocv_raw;
	s64 cc_at_ocv;
	s64 last_cc_raw;
	s64 total_cc_raw;
	bool cc_initialized;
};

/* The existing temperature consumer pins the same VADC provider for all reads.
 * Use its public channel descriptors; never program ADC registers behind it.
 */
static int bms_adc_raw(struct bms_device_info *di, int number, int *value)
{
	struct iio_channel chan = { .indio_dev = di->adc->indio_dev };
	int i;
	for (i = 0; i < chan.indio_dev->num_channels; i++)
		if (chan.indio_dev->channels[i].channel == number) {
			chan.channel = &chan.indio_dev->channels[i];
			return iio_read_channel_raw(&chan, value);
		}
	return -ENODEV;
}

static int bms_adc_uv(struct bms_device_info *di, int raw, int *uv)
{
	int lo, hi, ret;
	ret = bms_adc_raw(di, 9, &lo);
	if (ret < 0)
		return ret;
	ret = bms_adc_raw(di, 10, &hi);
	if (ret < 0)
		return ret;
	if (hi <= lo || hi - lo < 1000)
		return -ERANGE;
	*uv = 3 * (625000 + div_s64((s64)(raw-lo)*625000, hi-lo));
	return (*uv < 2500000 || *uv > 4600000) ? -ERANGE : 0;
}

static int column_capacity(u32 voltage, struct bms_ocv_lut *lut, int col)
{
	int i;
	if (voltage >= lut->lut[0][col])
		return lut->capacity_legend[0];
	for (i = 0; i < lut->rows-1; i++)
		if (voltage >= lut->lut[i+1][col])
			return fixp_linear_interpolate(lut->lut[i][col], lut->capacity_legend[i],
				lut->lut[i+1][col], lut->capacity_legend[i+1], voltage);
	return lut->capacity_legend[lut->rows-1];
}

static bool __maybe_unused between(int left, int right, int val)
{
	if (left <= val && val <= right)
		return true;

	if (left >= val && val >= right)
		return true;

	return false;
}

static int interpolate_capacity(int temp, u32 ocv,
				struct bms_ocv_lut *ocv_lut)
{
	int j;
	/* Bound each column separately, including temperatures outside the LUT. */
	if (temp <= ocv_lut->temp_legend[0])
		return column_capacity(ocv, ocv_lut, 0);
	for (j = 1; j < TEMPERATURE_COLS; j++)
		if (temp <= ocv_lut->temp_legend[j])
			return fixp_linear_interpolate(ocv_lut->temp_legend[j-1],
				column_capacity(ocv, ocv_lut, j-1), ocv_lut->temp_legend[j],
				column_capacity(ocv, ocv_lut, j), temp);
	return column_capacity(ocv, ocv_lut, TEMPERATURE_COLS-1);

#if 0 /* Retained for comparison with the original unsafe indexing. */
	int pcj_minus_one = 0, pcj = 0, i2 = 0, i3 = 0, i;
	for (j = 0; j < TEMPERATURE_COLS; j++)
		if (temp <= ocv_lut->temp_legend[j])
			break;

	if (ocv >= ocv_lut->lut[0][j])
		return ocv_lut->capacity_legend[0];

	if (ocv <= ocv_lut->lut[ocv_lut->rows-1][j-1])
		return ocv_lut->capacity_legend[ocv_lut->rows-1];

	for (i = 0; i < ocv_lut->rows-1; i++) {
		if (between(ocv_lut->lut[i][j],
			    ocv_lut->lut[i+1][j], ocv))
			i2 = i;

		if (between(ocv_lut->lut[i][j-1],
			    ocv_lut->lut[i+1][j-1], ocv))
			i3 = i;
	}

	/* interpolate two capacities */
	pcj = fixp_linear_interpolate(ocv_lut->lut[i2][j],
				      ocv_lut->capacity_legend[i2],
				      ocv_lut->lut[i2+1][j],
				      ocv_lut->capacity_legend[i2+1],
				      ocv);

	pcj_minus_one = fixp_linear_interpolate(ocv_lut->lut[i3][j-1],
						ocv_lut->capacity_legend[i3],
						ocv_lut->lut[i3+1][j-1],
						ocv_lut->capacity_legend[i3+1],
						ocv);

	/* interpolate them with the battery temperature */
	return fixp_linear_interpolate(ocv_lut->temp_legend[j-1],
				       pcj_minus_one,
				       ocv_lut->temp_legend[j],
				       pcj,
				       temp);
#endif
}

static int interpolate_fcc(int temp, struct bms_fcc_lut *fcc_lut)
{
	int i;
	if (temp <= fcc_lut->temp_legend[0])
		return fcc_lut->lut[0];
	if (temp >= fcc_lut->temp_legend[TEMPERATURE_COLS-1])
		return fcc_lut->lut[TEMPERATURE_COLS-1];

	for (i = 0; i < TEMPERATURE_COLS; i++)
		if (temp <= fcc_lut->temp_legend[i])
			break;

	return fixp_linear_interpolate(fcc_lut->temp_legend[i-1],
			     fcc_lut->lut[i-1],
			     fcc_lut->temp_legend[i],
			     fcc_lut->lut[i],
			     temp);
}

static int bms_lock_output_data(struct bms_device_info *di)
{
	int ret;

	ret = regmap_update_bits(di->regmap, di->base_addr +
				 REG_BMS_CC_DATA_CTL,
				 BMS_HOLD_OREG_DATA, BMS_HOLD_OREG_DATA);
	if (ret) {
		dev_err(di->dev, "failed to lock bms output: %d", ret);
		return ret;
	}

	/*
	 * Sleep for at least 100 microseconds here to make sure
	 * there has been at least three cycles of the sleep clock
	 * so that the registers are correctly locked.
	 */
	usleep_range(100, 1000);

	return 0;
}


static int bms_unlock_output_data(struct bms_device_info *di)
{
	int ret;

	ret = regmap_update_bits(di->regmap, di->base_addr +
				 REG_BMS_CC_DATA_CTL,
				 BMS_HOLD_OREG_DATA, 0);
	if (ret) {
		dev_err(di->dev, "failed to unlock bms output: %d", ret);
		return ret;
	}

	return 0;
}

static int bms_read_ocv(struct bms_device_info *di, u32 *ocv)
{
	int ret;
	__le16 read_ocv;
	int uv;

	mutex_lock(&di->bms_output_lock);

	ret = bms_lock_output_data(di);
	if (ret)
		goto err_lock;

	ret = regmap_bulk_read(di->regmap, di->base_addr+
			       REG_BMS_OCV_FOR_SOC_DATA0, &read_ocv, 2);
	if (ret) {
		dev_err(di->dev, "open circuit voltage read failed: %d", ret);
		goto err_read;
	}

	dev_dbg(di->dev, "read open circuit voltage of: %d mv", read_ocv);


	di->ocv_raw = le16_to_cpu(read_ocv);
	ret = bms_adc_uv(di, di->ocv_raw, &uv);
	if (!ret)
		*ocv = uv;

err_read:
	bms_unlock_output_data(di);

err_lock:
	mutex_unlock(&di->bms_output_lock);

	return ret;
}

static int bms_read_cc(struct bms_device_info *di, s64 *cc_uah)
{
	int ret;
	u8 bytes[5];
	s64 cc_raw, quotient, remainder;

	mutex_lock(&di->bms_output_lock);

	ret = bms_lock_output_data(di);
	if (ret)
		goto err_lock;

	ret = regmap_bulk_read(di->regmap, di->base_addr +
			       REG_BMS_SHDW_CC_DATA0,
			       bytes, 5);
	if (ret) {
		dev_err(di->dev, "coulomb counter read failed: %d", ret);
		goto err_read;
	}
	cc_raw = sign_extend64((u64)get_unaligned_le32(bytes) | ((u64)bytes[4] << 32), 35);
	if (!di->cc_initialized) {
		di->total_cc_raw = cc_raw;
		di->cc_initialized = true;
	} else {
		di->total_cc_raw += sign_extend64((cc_raw-di->last_cc_raw) & ((1ULL << 36)-1), 35);
	}
	di->last_cc_raw = cc_raw;
	cc_raw = di->total_cc_raw;

	ret = bms_unlock_output_data(di);
	if (ret)
		goto err_lock;

	mutex_unlock(&di->bms_output_lock);

	/* Exact reduced form of Qualcomm's 36-bit CC conversion, 10 mOhm.
	 * (542535/100000) * 56 * 1e6 / (32764 * 3600 * 10000).
	 * Split before multiplying so extended counters do not overflow.
	 */
	quotient = div_s64(cc_raw, 982920000);
	remainder = cc_raw - quotient * 982920000;
	*cc_uah = quotient * 253183 + div_s64(remainder * 253183, 982920000);

	dev_dbg(di->dev, "read coulomb counter value of: %lld uah", *cc_uah);

	return 0;

err_read:
	bms_unlock_output_data(di);

err_lock:
	mutex_unlock(&di->bms_output_lock);

	return ret;
}

static void __maybe_unused bms_reset_cc(struct bms_device_info *di)
{
	int ret;

	mutex_lock(&di->bms_output_lock);

	ret = regmap_update_bits(di->regmap, di->base_addr +
				 REG_BMS_CC_CLEAR_CTL,
				 BMS_CLEAR_SHDW_CC,
				 BMS_CLEAR_SHDW_CC);
	if (ret) {
		dev_err(di->dev, "coulomb counter reset failed: %d", ret);
		goto err_lock;
	}

	/* wait at least three sleep cycles for cc to reset */
	usleep_range(100, 1000);

	ret = regmap_update_bits(di->regmap, di->base_addr +
				 REG_BMS_CC_CLEAR_CTL,
				 BMS_CLEAR_SHDW_CC, 0);
	if (ret)
		dev_err(di->dev, "coulomb counter re-enable failed: %d", ret);

err_lock:
	mutex_unlock(&di->bms_output_lock);
}

static int bms_calculate_capacity(struct bms_device_info *di, int *capacity)
{
	unsigned long fcc;
	int ret, temp, ocv_capacity, temp_degc;
	s64 cc = 0;

	/* BAT_THERM is raw voltage, NOT milli-Celsius. The battery-specific NTC
	 * curve is unverified, so use the nominal 25 C LUT and expose no fake temp.
	 */
	temp = 25000;
	temp_degc = temp / 1000;

	ret = bms_read_cc(di, &cc);
	if (ret < 0) {
		dev_err(di->dev, "failed to read coulomb counter: %d", ret);
		return ret;
	}
	cc -= di->cc_at_ocv;

	/* interpolate capacity from open circuit voltage */
	ocv_capacity = interpolate_capacity(temp_degc, di->ocv,
					    &di->ocv_lut);

	/* interpolate the full charge capacity from temperature */
	fcc = interpolate_fcc(temp_degc, &di->fcc_lut);

	/* append coloumb counter to capacity */
	*capacity = DIV_ROUND_CLOSEST(fcc * ocv_capacity, 100);
	*capacity = div_s64((*capacity - cc) * 100, fcc);
	*capacity = clamp(*capacity, 0, 100);

	return 0;
}



/*
 * Return power_supply property
 */
static int pm8941_bms_battery_get_property(struct power_supply *psy,
				   enum power_supply_property psp,
				   union power_supply_propval *val)
{
	struct bms_device_info *di = power_supply_get_drvdata(psy);
	// struct power_supply_battery_info *info = di->info;

    int ret;
    int supplied;
	struct power_supply *charger;
	switch (psp) {
	case POWER_SUPPLY_PROP_STATUS:
		charger = power_supply_get_by_name("smbb-bif");
		if (!charger)
			return -ENODEV;
		ret = power_supply_get_property(charger, POWER_SUPPLY_PROP_STATUS, val);
		power_supply_put(charger);
		return ret;

#if 0
		supplied = power_supply_am_i_supplied(psy);

		if (supplied < 0 && supplied != -ENODEV)
			return supplied;
		else if (supplied && supplied != -ENODEV)
			val->intval = POWER_SUPPLY_STATUS_CHARGING;
		else
			val->intval = POWER_SUPPLY_STATUS_DISCHARGING;
		return 0;
#endif
	case POWER_SUPPLY_PROP_VOLTAGE_NOW:
		ret = bms_adc_raw(di, 6, &supplied);
		if (ret < 0)
			return ret;
		return bms_adc_uv(di, supplied, &val->intval);
	case POWER_SUPPLY_PROP_VOLTAGE_OCV:
		val->intval = di->ocv;
		return 0;
	case POWER_SUPPLY_PROP_CHARGE_COUNTER: {
		s64 cc;
		ret = bms_read_cc(di, &cc);
		if (ret < 0)
			return ret;
		val->intval = clamp_t(s64, cc, INT_MIN, INT_MAX);
		return 0;
	}

	// case POWER_SUPPLY_PROP_HEALTH:
	// 	if (bat->vbat_now < info->voltage_min_design_uv)
	// 		val->intval = POWER_SUPPLY_HEALTH_DEAD;
	// 	else if (bat->vbat_now > info->voltage_max_design_uv)
	// 		val->intval = POWER_SUPPLY_HEALTH_OVERVOLTAGE;
	// 	else
	// 		val->intval = POWER_SUPPLY_HEALTH_GOOD;
	// 	return 0;

	case POWER_SUPPLY_PROP_CAPACITY:
		mutex_lock(&di->sample_lock);
		ret = bms_calculate_capacity(di, &val->intval);
		mutex_unlock(&di->sample_lock);
		break;
	default:
		ret = -EINVAL;
		break;
	}

	if (val->intval == INT_MAX || val->intval == INT_MIN)
		ret = -EINVAL;

	return ret;
}

static enum power_supply_property pm8941_bms_battery_properties[] = {
	POWER_SUPPLY_PROP_CAPACITY,
    POWER_SUPPLY_PROP_STATUS,
    POWER_SUPPLY_PROP_VOLTAGE_NOW,
    POWER_SUPPLY_PROP_VOLTAGE_OCV,
    POWER_SUPPLY_PROP_CHARGE_COUNTER,
};

static irqreturn_t bms_ocv_thr_irq_handler(int irq, void *dev_id)
{
	struct bms_device_info *di = dev_id;
	s64 cc;
	u32 ocv;

	mutex_lock(&di->sample_lock);
	if (bms_read_ocv(di, &ocv) < 0 || bms_read_cc(di, &cc) < 0) {
		mutex_unlock(&di->sample_lock);
		return IRQ_HANDLED;
	}

	/* Do not clear counters via the original, unverified register offset. */
	di->cc_at_ocv = cc;
	di->ocv = ocv;
	mutex_unlock(&di->sample_lock);
	if (di->battery)
		power_supply_changed(di->battery);
	return IRQ_HANDLED;
}

static const struct power_supply_desc pm8941_bms_battery_psy_desc = {
	.name = "pm8941-bms",
	.type = POWER_SUPPLY_TYPE_BATTERY,
	.properties = pm8941_bms_battery_properties,
	.num_properties = ARRAY_SIZE(pm8941_bms_battery_properties),
	.get_property = pm8941_bms_battery_get_property,
};

static int bms_probe(struct platform_device *pdev)
{
	struct power_supply *bat;
	struct bms_device_info *di;
    struct power_supply_config psy_cfg = {};

	int ret;

	di = devm_kzalloc(&pdev->dev, sizeof(*di), GFP_KERNEL);
	if (!di)
		return -ENOMEM;

	di->dev = &pdev->dev;
	mutex_init(&di->bms_output_lock);
	mutex_init(&di->sample_lock);

	di->regmap = dev_get_regmap(pdev->dev.parent, NULL);
	if (!di->regmap) {
		dev_err(di->dev, "Unable to get regmap");
		return -EINVAL;
	}

	di->adc = devm_iio_channel_get(&pdev->dev, "temp");
	if (IS_ERR(di->adc))
		return PTR_ERR(di->adc);

	ret = of_property_read_u32(di->dev->of_node, "reg", &di->base_addr);
	if (ret < 0)
		return ret;

	ret = of_property_read_u8_array(di->dev->of_node,
						 "qcom,ocv-temp-legend-celsius",
						 (u8 *)di->ocv_lut.temp_legend,
						 TEMPERATURE_COLS);
	if (ret < 0) {
		dev_err(di->dev, "no open circuit voltage temperature legend found");
		return ret;
	}

	di->ocv_lut.rows = of_property_read_variable_u8_array(di->dev->of_node,
						 "qcom,ocv-capacity-legend",
						 di->ocv_lut.capacity_legend, 0,
						 MAX_CAPACITY_ROWS);
	if (di->ocv_lut.rows < 0) {
		dev_err(di->dev, "no open circuit voltage capacity legend found");
		return ret;
	}

	ret = of_property_read_variable_u32_array(di->dev->of_node,
						  "qcom,ocv-lut-microvolt",
						  (u32 *)di->ocv_lut.lut,
						  TEMPERATURE_COLS,
						  TEMPERATURE_COLS *
						  MAX_CAPACITY_ROWS);
	if (ret < 0) {
		dev_err(di->dev, "no open circuit voltage lut array found");
		return ret;
	}

	ret = of_property_read_u8_array(di->dev->of_node,
						 "qcom,fcc-temp-legend-celsius",
						 (u8 *)di->fcc_lut.temp_legend,
						 TEMPERATURE_COLS);
	if (ret < 0) {
		dev_err(di->dev, "no full charge capacity temperature legend found");
		return ret;
	}

	ret = of_property_read_u32_array(di->dev->of_node,
						  "qcom,fcc-lut-microamp-hours",
						  di->fcc_lut.lut,
						  TEMPERATURE_COLS);
	if (ret < 0) {
		dev_err(di->dev, "no full charge capacity lut array found");
		return ret;
	}

	ret = bms_read_ocv(di, &di->ocv);
	if (ret < 0) {
		dev_err(di->dev, "failed to read initial open circuit voltage: %d",
			ret);
		return ret;
	}

	mutex_init(&di->bms_output_lock);
	dev_info(di->dev, "mi4-bms-fixed: OCV raw=%u calibrated=%u uV; nominal 25C LUT; 10mOhm sense assumption\n",
		 di->ocv_raw, di->ocv);

	di->ocv_thr_irq = platform_get_irq_byname(pdev, "ocv_thr");

	ret = devm_request_threaded_irq(di->dev, di->ocv_thr_irq, NULL,
					bms_ocv_thr_irq_handler,
					IRQF_TRIGGER_RISING | IRQF_ONESHOT,
					pdev->name, di);
	if (ret < 0) {
		dev_err(di->dev, "failed to request handler for open circuit voltage threshold IRQ");
		return ret;
	}


	di->bat_desc.name = "bms";
	di->bat_desc.type = POWER_SUPPLY_TYPE_BATTERY;
	di->bat_desc.properties = pm8941_bms_battery_properties;
	di->bat_desc.num_properties = ARRAY_SIZE(pm8941_bms_battery_properties);
	di->bat_desc.get_property = pm8941_bms_battery_get_property;

	psy_cfg.drv_data = di;
	bat = devm_power_supply_register(di->dev, &di->bat_desc, &psy_cfg);
	if (!IS_ERR(bat))
		di->battery = bat;
	//ret = power_supply_get_battery_info(di->dev, &di->info);
	//if (ret)
	//	return dev_err_probe(di->dev, ret, "Unable to get battery info\n");

	return PTR_ERR_OR_ZERO(bat);
}

static const struct of_device_id bms_of_match[] = {
	{.compatible = "qcom,pm8941-bms", },
	{ },
};
MODULE_DEVICE_TABLE(of, bms_of_match);

static struct platform_driver bms_driver = {
	.probe = bms_probe,
	.driver = {
		.name = "mi4-bms-fixed",
		.of_match_table = of_match_ptr(bms_of_match),
	},
};
module_platform_driver(bms_driver);

MODULE_AUTHOR("Craig Tatlor <ctatlor97@gmail.com>");
MODULE_DESCRIPTION("Qualcomm BMS driver");
MODULE_LICENSE("GPL");
MODULE_VERSION("1.0");
