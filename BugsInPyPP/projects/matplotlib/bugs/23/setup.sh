touch matplotlibrc
cp setup.cfg.template setup.cfg
sed -i 's|\[rc_options\]||g' setup.cfg
echo '[rc_options]' >> setup.cfg
echo 'tests = True' >> setup.cfg
echo 'ft2font = True' >> setup.cfg
echo 'path = True' >> setup.cfg
conda env config vars set MPLLOCALFREETYPE=1