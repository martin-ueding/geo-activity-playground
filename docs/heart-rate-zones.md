# Heart Rate Zones

The heart rate alone isn't too helpful, I feel. What puts it into perspective are the _heart rate zones_ which put the heart rate into certain intervals.

The definition of the heart rate zones is not standardized. Usually there are five zones and they have the same names. What differs is how their ranges are computed and there is some chaos around that.

All definitions that I found take the maximum heart rate as the upper limit. One can measure this as part of a professional training or just use the _220 minus age_ prescription which at least for me matches close enough. What they differ on is how they use a lower bound. It seems that [Polar](https://www.polar.com/blog/running-heart-rate-zones-basics/) or [REI](https://www.rei.com/learn/expert-advice/how-to-train-with-a-heart-rate-monitor.html) basically use 0 as the lower bound. My Garmin system also uses 0 as the lower bound. But as one can see in [this blog](https://theathleteblog.com/heart-rate-zones/), one can also use the resting heart rate as the lower bound.

Based on the maximum and resting heart rate we will then compute the heart rate zones using certain percentages of _effort_. We can compute the heart rate as the following:

> rate = effort × (maximum – minimum) + minimum

The zones then take the following efforts:

Zone | Effort | Training
---: | ---: | ---:
1 | 50 to 60 % | Warmup/Recovery
2 | 60 to 70 % | Base Fitness
3 | 70 to 80 % | Aerobic Endurance
4 | 80 to 90 % | Anerobic Capacity
5 | 90 to 100 % | Speed Training

You can decide how you want to do work with that. If you want to have the same definitions that say Garmin uses, you need to just enter your birth year and we can compute the rest. If you want to use a lower bound, you need to specify that.