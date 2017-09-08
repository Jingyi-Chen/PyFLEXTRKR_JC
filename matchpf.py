# Purpose: match mergedir tracked MCS with NMQ CSA to calculate radar-based statsitics underneath the cloud features.

# Author: Original IDL code written by Zhe Feng (zhe.feng@pnnl.gov), Python version written by Hannah C. Barnes (hannah.barnes@pnnl.gov)

def identifypf_mergedir_nmq(mcsstats_filebase, cloudid_filebase, stats_path, cloudidtrack_path, pfdata_path, rainaccumulation_path, startdate, enddate, geolimits, nmaxpf, nmaxcore, nmaxpix, nmaxclouds, rr_min, pixel_radius, irdatasource, nmqdatasource, datadescription, datatimeresolution, mcs_irareathresh, mcs_irdurationthresh, mcs_ireccentricitythresh):
    import numpy as np
    import os.path
    from netCDF4 import Dataset
    from scipy.ndimage import label, binary_dilation, generate_binary_structure
    from skimage.measure import regionprops
    import matplotlib.pyplot as plt
    from math import pi
    from scipy.stats import skew
    import xarray as xr
    import time

    np.set_printoptions(threshold=np.inf)

    #########################################################
    # Set constants
    fillvalue = -9999

    #########################################################
    # Load MCS track stats
    mcsirstatistics_file = stats_path + mcsstats_filebase + startdate + '_' + enddate + '.nc'
    print(mcsirstatistics_file)

    mcsirstatdata = Dataset(mcsirstatistics_file, 'r')
    ir_ntracks = len(mcsirstatdata.dimensions['ntracks']) # Total number of tracked features
    ir_nmaxlength = len(mcsirstatdata.dimensions['ntimes']) # Maximum number of features in a given track
    ir_nmaxmergesplits = len(mcsirstatdata.dimensions['nmergers']) # Maximum number of features in a given track
    ir_description = str(Dataset.getncattr(mcsirstatdata, 'description'))
    ir_source = str(Dataset.getncattr(mcsirstatdata, 'source'))
    ir_time_res = str(Dataset.getncattr(mcsirstatdata, 'time_resolution_hour'))
    ir_pixel_radius = str(Dataset.getncattr(mcsirstatdata, 'pixel_radius_km'))
    mcsarea_thresh = str(Dataset.getncattr(mcsirstatdata, 'MCS_area_km**2'))
    mcsduration_thresh = str(Dataset.getncattr(mcsirstatdata, 'MCS_duration_hour'))
    mcseccentricity_thresh = str(Dataset.getncattr(mcsirstatdata, 'MCS_eccentricity'))
    ir_basetime = mcsirstatdata.variables['mcs_basetime'][:] # time of each cloud in mcs track
    ir_datetimestring = mcsirstatdata.variables['mcs_datetimestring'][:] # time of each cloud in mcs track
    ir_mcslength = mcsirstatdata.variables['mcs_length'][:] # duration of mcs track
    ir_tracklength = mcsirstatdata.variables['track_length'][:] # duration of full track containing an mcs
    ir_meanlat = mcsirstatdata.variables['mcs_meanlat'][:] # mean latitude of the core and cold anvil of each cloud in mcs track
    ir_meanlon = mcsirstatdata.variables['mcs_meanlon'][:] # mean longitude of the core and cold anvil of each cloud in mcs track
    ir_corearea = mcsirstatdata.variables['mcs_corearea'][:] # area of each cold core in mcs track
    ir_ccsarea = mcsirstatdata.variables['mcs_ccsarea'][:] # area of each cold core + cold anvil in mcs track
    ir_cloudnumber = mcsirstatdata.variables['mcs_cloudnumber'][:] # number that corresponds to this cloud in the pixel level cloudid files
    ir_mergecloudnumber = mcsirstatdata.variables['mcs_mergecloudnumber'][:] # Cloud number of a small cloud that merges into an MCS
    ir_splitcloudnumber = mcsirstatdata.variables['mcs_splitcloudnumber'][:] # Cloud number of asmall cloud that splits from an MCS
    ir_type = mcsirstatdata.variables['mcs_type'][:] # type of mcs
    ir_status = mcsirstatdata.variables['mcs_status'][:] # flag describing how clouds in mcs track change over time
    ir_startstatus = mcsirstatdata.variables['mcs_startstatus'][:] # status of the first cloud in the mcs
    ir_endstatus = mcsirstatdata.variables['mcs_endstatus'][:] # status of the last cloud in the mcs
    ir_boundary = mcsirstatdata.variables['mcs_boundary'][:] # flag indicating whether the mcs track touches the edge of the data
    ir_interruptions = mcsirstatdata.variables['mcs_trackinterruptions'][:] # flag indicating if break exists in the track data
    mcsirstatdata.close()

    ###################################################################
    # Intialize precipitation statistic matrices

    # Variables for each precipitation feature
    radar_npf = np.ones((ir_ntracks, ir_nmaxlength), dtype=int)*fillvalue
    radar_pflon = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pflat = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfnpix = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfrainrate = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfskewness = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfmajoraxis = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfminoraxis = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfaspectratio = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pforientation = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfeccentricity = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfdbz40npix = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfdbz45npix = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue
    radar_pfdbz50npix = np.ones((ir_ntracks, ir_nmaxlength, nmaxpf), dtype=float)*fillvalue

    # Variables average for the largest few precipitation features
    radar_ccavgrainrate = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_ccavgnpix = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_ccavgdbz10 = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_ccavgdbz20 = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_ccavgdbz30 = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_ccavgdbz40 = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_sfavgnpix = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue
    radar_sfavgrainrate = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue

    # Variables for each convective core
    radar_ccncores = np.ones((ir_ntracks, ir_nmaxlength), dtype=int)*fillvalue
    radar_cclon = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_cclat = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccnpix = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccxcentroid = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccycentroid = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccxweightedcentroid = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccyweightedcentroid = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccmajoraxis = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccminoraxis = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccaspectratio = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccorientation = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccperimeter = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_cceccentricity = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccmaxdbz10 = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccmaxdbz20 = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccmaxdbz30 = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccmaxdbz40 = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccdbz10mean = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccdbz20mean = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccdbz30mean = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue
    radar_ccdbz40mean = np.ones((ir_ntracks, ir_nmaxlength, nmaxcore), dtype=float)*fillvalue

    radar_pffrac = np.ones((ir_ntracks, ir_nmaxlength), dtype=float)*fillvalue

    # Variables for accumulated rainfall
    radar_nuniqpix = np.ones(ir_ntracks, dtype=float)*fillvalue
    radar_locidx = np.ones((ir_ntracks, nmaxpix), dtype=float)*fillvalue
    radar_durtime = np.ones((ir_ntracks, nmaxpix), dtype=float)*fillvalue
    radar_durrainrate = np.ones((ir_ntracks, nmaxpix), dtype=float)*fillvalue

    ##############################################################
    # Find precipitation feature in each mcs

    # Loop over each track
    for it in range(0, ir_ntracks):
        print('Processing track ' + str(int(it)))

        # Isolate ir statistics about this track
        ittracklength = np.copy(ir_tracklength[it])
        itmcslength = np.copy(ir_mcslength[it])
        itbasetime = np.copy(ir_basetime[it, :])
        itdatetimestring = np.copy(ir_datetimestring[it][:][:])
        itstatus = np.copy(ir_status[it, :])
        itcloudnumber = np.copy(ir_cloudnumber[it, :])
        itmergecloudnumber = np.copy(ir_mergecloudnumber[it, :, :])
        itsplitcloudnumber = np.copy(ir_splitcloudnumber[it, :, :])

        # Loop through each time in the track
        irindices = np.array(np.where(itbasetime > 0))[0, :]
        for itt in irindices:
            # Isolate the data at this time
            ittbasetime = np.copy(itbasetime[itt])
            ittstatus = np.copy(itstatus[itt])
            ittcloudnumber = np.copy(itcloudnumber[itt])
            ittmergecloudnumber = np.copy(itmergecloudnumber[itt, :])
            ittsplitcloudnumber = np.copy(itsplitcloudnumber[itt, :])
            ittdatetimestring = np.copy(itdatetimestring[itt])

            if ittdatetimestring[11:12] == '0':
                # Generate date file names
                ittdatetimestring = ''.join(ittdatetimestring)
                cloudid_filename = cloudidtrack_path + cloudid_filebase + ittdatetimestring + '.nc'
                radar_filename = pfdata_path + 'csa4km_' + ittdatetimestring + '00.nc'
                rainaccumulation_filename = rainaccumulation_path + 'regrid_q2_' + ittdatetimestring[0:8] + '.' + ittdatetimestring[9::] + '00.nc'

                statistics_outfile = stats_path + 'mcs_tracks_'  + nmqdatasource + '_' + startdate + '_' + enddate + '.nc'

                ########################################################################
                # Load data

                # Load cloudid and precip feature data
                if os.path.isfile(cloudid_filename) and os.path.isfile(radar_filename):
                    # Load cloudid data
                    print(cloudid_filename)
                    cloudiddata = Dataset(cloudid_filename, 'r')
                    rawirlat = cloudiddata.variables['latitude'][:]
                    rawirlon = cloudiddata.variables['longitude'][:]
                    rawtbmap = cloudiddata.variables['tb'][:]
                    rawcloudnumbermap = cloudiddata.variables['cloudnumber'][:]
                    cloudiddata.close()

                    # Read precipitation data
                    print(radar_filename)
                    pfdata = Dataset(radar_filename, 'r')
                    rawpflat = pfdata.variables['lat2d'][:]
                    rawpflon = pfdata.variables['lon2d'][:]
                    rawdbzmap = pfdata.variables['dbz_convsf'][:] # map of reflectivity 
                    rawdbz10map = pfdata.variables['dbz10_height'][:] # map of 10 dBZ ETHs
                    rawdbz20map = pfdata.variables['dbz20_height'][:] # map of 20 dBZ ETHs
                    rawdbz30map = pfdata.variables['dbz30_height'][:] # map of 30 dBZ ETHs
                    rawdbz40map = pfdata.variables['dbz40_height'][:] # map of 40 dBZ ETHs
                    rawdbz45map = pfdata.variables['dbz45_height'][:] # map of 45 dBZ ETH
                    rawdbz50map = pfdata.variables['dbz50_height'][:] # map of 50 dBZ ETHs
                    rawcsamap = pfdata.variables['csa'][:] # map of convective, stratiform, anvil categories
                    rawrainratemap = pfdata.variables['rainrate'][:] # map of rain rate
                    rawpfnumbermap = pfdata.variables['pf_number'][:] # map of the precipitation feature number attributed to that pixel
                    rawdataqualitymap = pfdata.variables['mask'][:] # map if good (1) and bad (0) data
                    rawpfxspacing = pfdata.variables['x_spacing'][:] # distance between grid points in x direction
                    rawpfyspacing = pfdata.variables['y_spacing'][:] # distance between grid points in y direction
                    pfdata.close()

                    # Fill missing data with fill value so consistent with other data
                    rawdbzmap = np.ma.filled(rawdbzmap.astype(float), fillvalue)
                    rawdbz10map = np.ma.filled(rawdbz10map.astype(float), fillvalue)
                    rawdbz20map = np.ma.filled(rawdbz20map.astype(float), fillvalue)
                    rawdbz30map = np.ma.filled(rawdbz30map.astype(float), fillvalue)
                    rawdbz40map = np.ma.filled(rawdbz40map.astype(float), fillvalue)
                    rawdbz45map = np.ma.filled(rawdbz40map.astype(float), fillvalue)
                    rawdbz50map = np.ma.filled(rawdbz40map.astype(float), fillvalue)
                    rawcsamap = np.ma.filled(rawcsamap.astype(float), fillvalue)
                    rawrainratemap = np.ma.filled(rawrainratemap.astype(float), fillvalue)
                    rawpfnumbermap = np.ma.filled(rawpfnumbermap.astype(float), fillvalue)
                    rawdataqualitymap = np.ma.filled(rawdataqualitymap.astype(float), fillvalue)

                    # Load accumulation data is available. If not present fill array with fill value
                    if os.path.isfile(rainaccumulation_filename):
                        rainaccumulationdata = Dataset(rainaccumulation_filename, 'r')
                        rawrainaccumulationmap = rainaccumulationdata.variables['precipitation'][:]
                        rainaccumulationdata.close()

                        rawrainaccumulationmap = np.ma.filled(rawrainaccumulationmap.astype(float), fillvalue)
                    else:
                        rawrainaccumulationmap = np.ones((ny, nx), dtype=float)*fillvalue

                    ##########################################################################
                    # Get dimensions of data. Data should be preprocesses so that their latittude and longitude dimensions are the same
                    ydim, xdim = np.shape(rawirlat)


                    #########################################################################
                    # Intialize matrices for only MCS data
                    filteredrainratemap = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbzmap = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz10map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz20map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz30map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz40map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz45map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filtereddbz50map = np.ones((ydim, xdim), dtype=float)*fillvalue
                    filteredcsamap = np.zeros((ydim, xdim), dtype=int)

                    ############################################################################
                    # Find matching cloud number
                    icloudlocationt, icloudlocationy, icloudlocationx = np.array(np.where(rawcloudnumbermap == ittcloudnumber))
                    ncloudpix = len(icloudlocationy)

                    if ncloudpix > 0:
                        ######################################################################
                        # Check if any small clouds merge
                        idmergecloudnumber = np.array(np.where(ittmergecloudnumber > 0))[0, :]
                        nmergecloud = len(idmergecloudnumber)

                        if nmergecloud > 0:
                            # Loop over each merging cloud
                            for imc in idmergecloudnumber:
                                # Find location of the merging cloud
                                imergelocationt, imergelocationy, imergelocationx = np.array((np.where(rawcloudnumbermap == ittmergecloudnumber[imc])))
                                nmergepix = len(imergelocationy)

                                # Add merge pixes to mcs pixels
                                if nmergepix > 0:
                                    icloudlocationt = np.hstack((icloudlocationt, imergelocationt))
                                    icloudlocationy = np.hstack((icloudlocationy, imergelocationy))
                                    icloudlocationx = np.hstack((icloudlocationx, imergelocationx))

                        ######################################################################
                        # Check if any small clouds split
                        idsplitcloudnumber = np.array(np.where(ittsplitcloudnumber > 0))[0, :]
                        nsplitcloud = len(idsplitcloudnumber)

                        if nsplitcloud > 0:
                            # Loop over each merging cloud
                            for imc in idsplitcloudnumber:
                                # Find location of the merging cloud
                                isplitlocationt, isplitlocationy, isplitlocationx = np.array((np.where(rawcloudnumbermap == ittsplitcloudnumber[imc])))
                                nsplitpix = len(isplitlocationy)

                                # Add split pixes to mcs pixels
                                if nsplitpix > 0:
                                    icloudlocationt = np.hstack((icloudlocationt, isplitlocationt))
                                    icloudlocationy = np.hstack((icloudlocationy, isplitlocationy))
                                    icloudlocationx = np.hstack((icloudlocationx, isplitlocationx))

                        ########################################################################
                        # Fill matrices with mcs data
                        filteredrainratemap[icloudlocationy, icloudlocationx] = np.copy(rawrainratemap[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbzmap[icloudlocationy, icloudlocationx] = np.copy(rawdbzmap[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz10map[icloudlocationy, icloudlocationx] = np.copy(rawdbz10map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz20map[icloudlocationy, icloudlocationx] = np.copy(rawdbz20map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz30map[icloudlocationy, icloudlocationx] = np.copy(rawdbz30map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz40map[icloudlocationy, icloudlocationx] = np.copy(rawdbz40map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz45map[icloudlocationy, icloudlocationx] = np.copy(rawdbz45map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filtereddbz50map[icloudlocationy, icloudlocationx] = np.copy(rawdbz50map[icloudlocationt, icloudlocationy, icloudlocationx])
                        filteredcsamap[icloudlocationy, icloudlocationx] = np.copy(rawcsamap[icloudlocationt, icloudlocationy, icloudlocationx])

                        #########################################################################
                        # isolate small region of cloud data around mcs at this time

                        # Set edges of boundary
                        miny = np.nanmin(icloudlocationy)
                        if miny <= 10:
                            miny = 0
                        else:
                            miny = miny - 10

                        maxy = np.nanmax(icloudlocationy)
                        if maxy >= ydim - 10:
                            maxy = ydim
                        else:
                            maxy = maxy + 11

                        minx = np.nanmin(icloudlocationx)
                        if minx <= 10:
                            minx = 0
                        else:
                            minx = minx - 10

                        maxx = np.nanmax(icloudlocationx)
                        if maxx >= xdim - 10:
                            maxx = xdim
                        else:
                            maxx = maxx + 11

                        # Isolate smaller region around cloud shield
                        subdbzmap = np.copy(filtereddbzmap[miny:maxy, minx:maxx])
                        subdbz10map = np.copy(filtereddbz10map[miny:maxy, minx:maxx])
                        subdbz20map = np.copy(filtereddbz20map[miny:maxy, minx:maxx])
                        subdbz30map = np.copy(filtereddbz30map[miny:maxy, minx:maxx])
                        subdbz40map = np.copy(filtereddbz40map[miny:maxy, minx:maxx])
                        subdbz50map = np.copy(filtereddbz50map[miny:maxy, minx:maxx])
                        subcsamap = np.copy(filteredcsamap[miny:maxy, minx:maxx])
                        subrainratemap = np.copy(filteredrainratemap[miny:maxy, minx:maxx])
                        sublat = np.copy(rawpflat[miny:maxy, minx:maxx])
                        sublon = np.copy(rawpflon[miny:maxy, minx:maxx])

                        #######################################################
                        # Get dimensions of subsetted region
                        subdimy, subdimx = np.shape(subdbzmap)

                        ######################################################
                        # Initialize convective map
                        ccflagmap = np.zeros((subdimy, subdimx), dtype=int)

                        #####################################################
                        # Get convective core statistics
                        icy, icx = np.array(np.where(subcsamap == 6))
                        nc = len(icy)

                        if nc  > 0 :
                            # Fill in convective map
                            ccflagmap[icy, icx] = 1

                            # Number convective regions
                            ccnumberlabelmap, ncc = label(ccflagmap)

                            # If convective cores exist calculate statistics
                            if ncc > 0:
                                # Initialize matrices
                                cclon = np.ones(ncc, dtype=float)*fillvalue
                                cclat = np.ones(ncc, dtype=float)*fillvalue
                                ccnpix = np.ones(ncc, dtype=float)*fillvalue
                                ccxcentroid = np.ones(ncc, dtype=float)*fillvalue
                                ccycentroid = np.ones(ncc, dtype=float)*fillvalue
                                ccxweightedcentroid = np.ones(ncc, dtype=float)*fillvalue
                                ccyweightedcentroid = np.ones(ncc, dtype=float)*fillvalue
                                ccmajoraxis = np.ones(ncc, dtype=float)*fillvalue
                                ccminoraxis = np.ones(ncc, dtype=float)*fillvalue
                                ccaspectratio = np.ones(ncc, dtype=float)*fillvalue
                                ccorientation = np.ones(ncc, dtype=float)*fillvalue
                                ccperimeter = np.ones(ncc, dtype=float)*fillvalue
                                cceccentricity = np.ones(ncc, dtype=float)*fillvalue
                                ccmaxdbz10 = np.ones(ncc, dtype=float)*fillvalue
                                ccmaxdbz20 = np.ones(ncc, dtype=float)*fillvalue
                                ccmaxdbz30 = np.ones(ncc, dtype=float)*fillvalue
                                ccmaxdbz40 = np.ones(ncc, dtype=float)*fillvalue
                                ccavgdbz10 = np.ones(ncc, dtype=float)*fillvalue
                                ccavgdbz20 = np.ones(ncc, dtype=float)*fillvalue
                                ccavgdbz30 = np.ones(ncc, dtype=float)*fillvalue
                                ccavgdbz40 = np.ones(ncc, dtype=float)*fillvalue

                                # Loop over each core
                                for cc in range(1, ncc+1):
                                    # Isolate core
                                    iiccy, iiccx = np.array(np.where(ccnumberlabelmap == cc))

                                    # Number of pixels in the core
                                    ccnpix[cc-1] = len(iiccy)

                                    # Get mean latitude and longitude
                                    cclon[cc-1] = np.nanmean(sublon[iiccy, iiccx])
                                    cclat[cc-1] = np.nanmean(sublat[iiccy, iiccx])

                                    # Get echo top height statistics
                                    ccmaxdbz10[cc-1] = np.nanmax(subdbz10map[iiccy, iiccx])
                                    ccmaxdbz10[cc-1] = np.nanmax(subdbz10map[iiccy, iiccx])
                                    ccmaxdbz20[cc-1] = np.nanmax(subdbz20map[iiccy, iiccx])
                                    ccmaxdbz30[cc-1] = np.nanmax(subdbz30map[iiccy, iiccx])
                                    ccmaxdbz40[cc-1] = np.nanmax(subdbz40map[iiccy, iiccx])
                                    ccavgdbz10[cc-1] = np.nanmean(subdbz10map[iiccy, iiccx])
                                    ccavgdbz20[cc-1] = np.nanmean(subdbz20map[iiccy, iiccx])
                                    ccavgdbz30[cc-1] = np.nanmean(subdbz30map[iiccy, iiccx])
                                    ccavgdbz40[cc-1] = np.nanmean(subdbz40map[iiccy, iiccx])

                                    # Generate map of convective core
                                    iiccflagmap = np.zeros((subdimy, subdimx), dtype=int)
                                    iiccflagmap[iiccy, iiccx] = 1

                                    # Get core geometric statistics
                                    coreproperties = regionprops(iiccflagmap, intensity_image=subdbzmap)
                                    cceccentricity[cc-1] = coreproperties[0].eccentricity
                                    ccmajoraxis[cc-1] = coreproperties[0].major_axis_length
                                    ccminoraxis[cc-1] = coreproperties[0].minor_axis_length
                                    ccaspectratio[cc-1] = np.divide(ccmajoraxis[cc-1], ccminoraxis[cc-1])
                                    ccorientation[cc-1] = (coreproperties[0].orientation)*(180/float(pi))
                                    ccperimeter[cc-1] = coreproperties[0].perimeter*pixel_radius
                                    ccycentroid[cc-1], ccxcentroid[cc-1] = coreproperties[0].centroid
                                    ccycentroid[cc-1] =  ccycentroid[cc-1] + miny
                                    ccxcentroid[cc-1] =  ccxcentroid[cc-1] + minx
                                    ccyweightedcentroid[cc-1], ccxweightedcentroid[cc-1] = coreproperties[0].weighted_centroid
                                    ccyweightedcentroid[cc-1] =  ccyweightedcentroid[cc-1] + miny
                                    ccxweightedcentroid[cc-1] =  ccxweightedcentroid[cc-1] + minx

                                ####################################################
                                # Sort based on size, largest to smallest
                                order = np.argsort(ccnpix)
                                order = order[::-1]

                                scclon = np.copy(cclon[order])
                                scclat = np.copy(cclat[order])
                                sccxcentroid = np.copy(ccxcentroid[order])
                                sccycentroid = np.copy(ccycentroid[order])
                                sccxweightedcentroid = np.copy(ccxweightedcentroid[order])
                                sccyweightedcentroid = np.copy(ccyweightedcentroid[order])
                                sccnpix = np.copy(ccnpix[order])
                                sccmajoraxis = np.copy(ccmajoraxis[order])
                                sccminoraxis = np.copy(ccminoraxis[order])
                                sccaspectratio = np.copy(ccaspectratio[order])
                                sccorientation = np.copy(ccorientation[order])
                                sccperimeter = np.copy(ccperimeter[order])
                                scceccentricity = np.copy(cceccentricity[order])
                                sccmaxdbz10 = np.copy(ccmaxdbz10[order])
                                sccmaxdbz20 = np.copy(ccmaxdbz20[order])
                                sccmaxdbz30 = np.copy(ccmaxdbz30[order])
                                sccmaxdbz40 = np.copy(ccmaxdbz40[order])
                                sccavgdbz10 = np.copy(ccavgdbz10[order])
                                sccavgdbz20 = np.copy(ccavgdbz20[order])
                                sccavgdbz30 = np.copy(ccavgdbz30[order])
                                sccavgdbz40 = np.copy(ccavgdbz40[order])

                                ###################################################
                                # Save convective core statisitcs
                                radar_ccncores[it, itt] = np.copy(ncc)

                                ncore_save = np.nanmin([nmaxcore, ncc])
                                radar_cclon[it, itt, 0:ncore_save-1] = np.copy(scclon[0:ncore_save-1])
                                radar_cclat[it, itt, 0:ncore_save-1] = np.copy(scclat[0:ncore_save-1])
                                radar_ccxcentroid[it, itt, 0:ncore_save-1] = np.copy(sccxcentroid[0:ncore_save-1])
                                radar_ccycentroid[it, itt, 0:ncore_save-1] = np.copy(sccycentroid[0:ncore_save-1])
                                radar_ccxweightedcentroid[it, itt, 0:ncore_save-1] = np.copy(sccxweightedcentroid[0:ncore_save-1])
                                radar_ccyweightedcentroid[it, itt, 0:ncore_save-1] = np.copy(sccyweightedcentroid[0:ncore_save-1])
                                radar_ccnpix[it, itt, 0:ncore_save-1] = np.copy(sccnpix[0:ncore_save-1])
                                radar_ccmajoraxis[it, itt, 0:ncore_save-1] = np.copy(sccmajoraxis[0:ncore_save-1])
                                radar_ccminoraxis[it, itt, 0:ncore_save-1] = np.copy(sccminoraxis[0:ncore_save-1])
                                radar_ccaspectratio[it, itt, 0:ncore_save-1] = np.copy(sccmajoraxis[0:ncore_save-1])
                                radar_ccorientation[it, itt, 0:ncore_save-1] = np.copy(sccorientation[0:ncore_save-1])
                                radar_ccperimeter[it, itt, 0:ncore_save-1] = np.copy(sccperimeter[0:ncore_save-1])
                                radar_cceccentricity[it, itt, 0:ncore_save-1] = np.copy(scceccentricity[0:ncore_save-1])
                                radar_ccmaxdbz10[it, itt, 0:ncore_save-1] = np.copy(sccmaxdbz10[0:ncore_save-1])
                                radar_ccmaxdbz20[it, itt, 0:ncore_save-1] = np.copy(sccmaxdbz20[0:ncore_save-1])
                                radar_ccmaxdbz30[it, itt, 0:ncore_save-1] = np.copy(sccmaxdbz30[0:ncore_save-1])
                                radar_ccmaxdbz40[it, itt, 0:ncore_save-1] = np.copy(sccmaxdbz40[0:ncore_save-1])
                                radar_ccdbz10mean[it, itt, 0:ncore_save-1] = np.copy(sccavgdbz10[0:ncore_save-1])
                                radar_ccdbz20mean[it, itt, 0:ncore_save-1] = np.copy(sccavgdbz20[0:ncore_save-1])
                                radar_ccdbz30mean[it, itt, 0:ncore_save-1] = np.copy(sccavgdbz30[0:ncore_save-1])
                                radar_ccdbz40mean[it, itt, 0:ncore_save-1] = np.copy(sccavgdbz40[0:ncore_save-1])

                            #######################################################
                            # Compute fraction of cloud within NMQ area
                            nmqct = np.shape(np.array(np.where(rawdataqualitymap[0, miny:maxy, minx:maxx] == 1)))[1]
                            otherct = np.shape(np.array(np.where(rawdataqualitymap[0, miny:maxy, minx:maxx] == 0)))[1]

                            radar_pffrac[it, itt] = np.divide(nmqct, nmqct + otherct)

                            ######################################################
                            # Derive precipitation feature statistics
                            ipfy, ipfx = np.array(np.where(((filteredcsamap == 5) | (filteredcsamap == 6)) & (filteredrainratemap > rr_min)))
                            nrainpix = len(ipfy)

                            if nrainpix > 0:
                                ####################################################
                                # Dilate precipitation feature by one pixel. This slightly smooths the data so that very close precipitation features are connected

                                # Create binary map
                                binarypfmap = np.zeros((ydim, xdim), dtype=int)
                                binarypfmap[ipfy, ipfx] = 1

                                # Dilate (aka smooth)
                                dilationstructure = generate_binary_structure(2,1)  # Defines shape of growth. This grows one pixel as a cross

                                dilatedbinarypfmap = binary_dilation(binarypfmap, structure=dilationstructure, iterations=1).astype(filteredrainratemap.dtype)

                                # Label precipitation features
                                pfnumberlabelmap, numpf = label(dilatedbinarypfmap)

                                if numpf > 0:

                                    ##############################################
                                    # Initialize matrices
                                    pfnpix = np.zeros(numpf, dtype=float)
                                    pfdbz40npix = np.zeros(numpf, dtype=float)
                                    pfdbz45npix = np.zeros(numpf, dtype=float)
                                    pfdbz50npix = np.zeros(numpf, dtype=float)
                                    pfid = np.ones(numpf, dtype=float)*fillvalue
                                    pflon = np.ones(numpf, dtype=float)*fillvalue
                                    pflat = np.ones(numpf, dtype=float)*fillvalue
                                    pfxcentroid = np.ones(numpf, dtype=float)*fillvalue
                                    pfycentroid = np.ones(numpf, dtype=float)*fillvalue
                                    pfxweightedcentroid = np.ones(numpf, dtype=float)*fillvalue
                                    pfyweightedcentroid = np.ones(numpf, dtype=float)*fillvalue
                                    pfrainrate = np.ones(numpf, dtype=float)*fillvalue
                                    pfskewness = np.ones(numpf, dtype=float)*fillvalue
                                    pfmajoraxis = np.ones(numpf, dtype=float)*fillvalue
                                    pfminoraxis = np.ones(numpf, dtype=float)*fillvalue
                                    pfaspectratio = np.ones(numpf, dtype=float)*fillvalue
                                    pfeccentricity = np.ones(numpf, dtype=float)*fillvalue
                                    pfperimeter = np.ones(numpf, dtype=float)*fillvalue
                                    pforientation = np.ones(numpf, dtype=float)*fillvalue

                                    pfccnpix = np.ones(numpf, dtype=float)*fillvalue
                                    pfccrainrate = np.ones(numpf, dtype=float)*fillvalue
                                    pfccdbz10 = np.ones(numpf, dtype=float)*fillvalue
                                    pfccdbz20 = np.ones(numpf, dtype=float)*fillvalue
                                    pfccdbz30 = np.ones(numpf, dtype=float)*fillvalue
                                    pfccdbz40 = np.ones(numpf, dtype=float)*fillvalue

                                    pfsfnpix = np.ones(numpf, dtype=float)*fillvalue
                                    pfsfrainrate = np.ones(numpf, dtype=float)*fillvalue

                                    ###############################################
                                    # Loop through each feature
                                    for ipf in range(1, numpf+1):

                                        #######################################
                                        # Find associated indices
                                        iipfy, iipfx = np.array(np.where(((pfnumberlabelmap == ipf)) & (filteredcsamap>=5) & (filteredcsamap<=6)))
                                        niipfpix = len(iipfy)

                                        if niipfpix > 0:
                                            ##########################################
                                            # Compute statistics

                                            # Basic statistics
                                            pfnpix[ipf-1] = np.copy(niipfpix)
                                            pfid[ipf-1] = np.copy(ipf)
                                            pfrainrate[ipf-1] = np.nanmean(filteredrainratemap[iipfy, iipfx])
                                            pfskewness[ipf-1] = skew(filteredrainratemap[iipfy, iipfx])
                                            pflon[ipf-1] = np.nanmean(rawpflat[iipfy, iipfx])
                                            pflat[ipf-1] = np.nanmean(rawpflon[iipfy, iipfx])

                                            # Generate map of convective core
                                            iipfflagmap = np.zeros((ydim, xdim), dtype=int)
                                            iipfflagmap[iipfy, iipfx] = 1

                                            # Geometric statistics
                                            pfproperties = regionprops(iipfflagmap, intensity_image=filteredrainratemap)
                                            pfeccentricity[ipf-1] = pfproperties[0].eccentricity
                                            pfmajoraxis[ipf-1] = pfproperties[0].major_axis_length
                                            # Need to treat minor axis length with an error except since the python algorthim occsionally throws an error. 
                                            try:
                                                pfminoraxis[ipf-1] = pfproperties[0].minor_axis_length
                                            except ValueError:
                                                pass
                                            if pfminoraxis[ipf-1]!=fillvalue or pfmajoraxis[ipf-1]!=fillvalue:
                                                pfaspectratio[ipf-1] = np.divide(pfmajoraxis[ipf-1], pfminoraxis[ipf-1])
                                            pforientation[ipf-1] = (pfproperties[0].orientation)*(180/float(pi))
                                            pfperimeter[ipf-1] = pfproperties[0].perimeter*pixel_radius
                                            [pfycentroid[ipf-1], pfxcentroid[ipf-1]] = pfproperties[0].centroid
                                            [pfyweightedcentroid[ipf-1], pfxweightedcentroid[ipf-1]] = pfproperties[0].weighted_centroid

                                            # Convective statistics
                                            iipfccy, iipfccx = np.array(np.where((pfnumberlabelmap == ipf) & (filteredcsamap == 6)))
                                            niipfcc = len(iipfccy)

                                            if niipfcc > 0:
                                                pfccnpix[ipf-1] = np.copy(niipfcc)
                                                pfccrainrate[ipf-1] = np.nanmean(filteredrainratemap[iipfccy, iipfccx])

                                                ifiltereddbz10map = np.copy(filtereddbz10map[iipfccy, iipfccx])
                                                ifiltereddbz10map = ifiltereddbz10map[ifiltereddbz10map != fillvalue]
                                                if len(ifiltereddbz10map) > 0:
                                                    pfccdbz10[ipf-1] = np.nanmean(ifiltereddbz10map)

                                                ifiltereddbz20map = np.copy(filtereddbz20map[iipfccy, iipfccx])
                                                ifiltereddbz20map = ifiltereddbz20map[ifiltereddbz20map != fillvalue]
                                                if len(ifiltereddbz20map) > 0:
                                                    pfccdbz20[ipf-1] = np.nanmean(ifiltereddbz20map)

                                                ifiltereddbz30map = np.copy(filtereddbz30map[iipfccy, iipfccx])
                                                ifiltereddbz30map = ifiltereddbz30map[ifiltereddbz30map != fillvalue]
                                                if len(ifiltereddbz30map) > 0:
                                                    pfccdbz30[ipf-1] = np.nanmean(ifiltereddbz30map)

                                                ifiltereddbz40map = np.copy(filtereddbz40map[iipfccy, iipfccx])
                                                ifiltereddbz40map = ifiltereddbz40map[ifiltereddbz40map != fillvalue]
                                                if len(ifiltereddbz40map) > 0:
                                                    pfccdbz40[ipf-1] = np.nanmean(ifiltereddbz40map)

                                            # Stratiform statistics
                                            iipfsy, iipfsx = np.array(np.where((pfnumberlabelmap == ipf) & (filteredcsamap == 5)))
                                            niipfs = len(iipfsy)

                                            if niipfs > 0:
                                                pfsfnpix[ipf-1] = np.copy(niipfs)
                                                pfsfrainrate[ipf-1] = np.nanmean(filteredrainratemap[iipfsy, iipfsx])

                                            # Find area exceeding echo top threshold
                                            pfdbz40npix[ipf-1] = len(np.array(np.where(filtereddbz40map[iipfy, iipfx] > 0))[0, :])
                                            pfdbz45npix[ipf-1] = len(np.array(np.where(filtereddbz45map[iipfy, iipfx] > 0))[0, :])
                                            pfdbz50npix[ipf-1] = len(np.array(np.where(filtereddbz50map[iipfy, iipfx] > 0))[0, :])

                                    ##############################################################
                                    # Sort precipitation features by size, large to small
                                    pforder = np.argsort(pfnpix)
                                    pforder = pforder[::-1]

                                    spfnpix = np.copy(pfnpix[pforder])
                                    spfid = np.copy(pfid[pforder])
                                    spfrainrate = np.copy(pfrainrate[pforder])
                                    spfskewness = np.copy(pfskewness[pforder])
                                    spflon = np.copy(pflon[pforder])
                                    spflat = np.copy(pflat[pforder])
                                    spfeccentricity = np.copy(pfeccentricity[pforder])
                                    spfmajoraxis = np.copy(pfmajoraxis[pforder])
                                    spfminoraxis = np.copy(pfminoraxis[pforder])
                                    spfaspectratio = np.copy(pfaspectratio[pforder])
                                    spforientation = np.copy(pforientation[pforder])
                                    spfycentroid = np.copy(pfycentroid[pforder])
                                    spfxcentroid = np.copy(pfxcentroid[pforder])
                                    spfxweightedcentroid = np.copy(pfxweightedcentroid[pforder])
                                    spfyweightedcentroid = np.copy(pfyweightedcentroid[pforder])
                                    spfccnpix = np.copy(pfccnpix[pforder])
                                    spfccrainrate = np.copy(pfccrainrate[pforder])
                                    spfccdbz10 = np.copy(pfccdbz10[pforder])
                                    spfccdbz20 = np.copy(pfccdbz20[pforder])
                                    spfccdbz30 = np.copy(pfccdbz30[pforder])
                                    spfccdbz40 = np.copy(pfccdbz40[pforder])
                                    spfsfnpix = np.copy(pfsfnpix[pforder])
                                    spfsfrainrate = np.copy(pfsfrainrate[pforder])
                                    spfdbz40npix = np.copy(pfdbz40npix[pforder])
                                    spfdbz45npix = np.copy(pfdbz45npix[pforder])
                                    spfdbz50npix = np.copy(pfdbz50npix[pforder])

                                    ###################################################
                                    # Save precipitation feature statisitcs
                                    radar_npf[it, itt] = np.copy(numpf)

                                    nradar_save = np.nanmin([nmaxpf, numpf])
                                    radar_pflon[it, itt, 0:nradar_save]= np.copy(spflon[0:nradar_save])
                                    radar_pflat[it, itt, 0:nradar_save] = np.copy(spflat[0:nradar_save])
                                    radar_pfnpix[it, itt, 0:nradar_save] = np.copy(spfnpix[0:nradar_save])
                                    radar_pfrainrate[it, itt, 0:nradar_save] = np.copy(spfrainrate[0:nradar_save])
                                    radar_pfskewness[it, itt, 0:nradar_save] = np.copy(spfskewness[0:nradar_save])
                                    radar_pfmajoraxis[it, itt, 0:nradar_save] = np.copy(spfmajoraxis[0:nradar_save])
                                    radar_pfminoraxis[it, itt, 0:nradar_save] = np.copy(spfminoraxis[0:nradar_save])
                                    radar_pfaspectratio[it, itt, 0:nradar_save] = np.copy(spfaspectratio[0:nradar_save])
                                    radar_pforientation[it, itt, 0:nradar_save] = np.copy(spforientation[0:nradar_save])
                                    radar_pfeccentricity[it, itt, 0:nradar_save] = np.copy(spfeccentricity[0:nradar_save])
                                    radar_pfdbz40npix[it, itt, 0:nradar_save] = np.copy(spfdbz40npix[0:nradar_save])
                                    radar_pfdbz45npix[it, itt, 0:nradar_save] = np.copy(spfdbz45npix[0:nradar_save])
                                    radar_pfdbz50npix[it, itt, 0:nradar_save] = np.copy(spfdbz50npix[0:nradar_save])

                                    ####################################################
                                    # Average the first twe largest precipitation features to represent the cloud system
                                    radar_ccavgnpix[it, itt] = np.nansum(spfccnpix[0:nradar_save])
                                    if radar_ccavgnpix[it, itt] != fillvalue:
                                        radar_ccavgrainrate[it, itt] = np.nanmean(spfccrainrate[np.where(spfccrainrate[0:nradar_save] != fillvalue)])

                                        ispfccdbz10 = np.copy(spfccdbz10[0:nradar_save])
                                        ispfccdbz10 = ispfccdbz10[ispfccdbz10 != fillvalue]
                                        if len(ispfccdbz10) > 0:
                                            radar_ccavgdbz10[it, itt] = np.nanmean(ispfccdbz10)

                                        ispfccdbz20 = np.copy(spfccdbz20[0:nradar_save])
                                        ispfccdbz20 = ispfccdbz20[ispfccdbz20 != fillvalue]
                                        if len(ispfccdbz20) > 0:
                                            radar_ccavgdbz20[it, itt] = np.nanmean(ispfccdbz20)

                                        ispfccdbz30 = np.copy(spfccdbz30[0:nradar_save])
                                        ispfccdbz30 = ispfccdbz30[ispfccdbz30 != fillvalue]
                                        if len(ispfccdbz30) > 0:
                                            radar_ccavgdbz30[it, itt] = np.nanmean(ispfccdbz30)

                                        ispfccdbz40 = np.copy(spfccdbz40[0:nradar_save])
                                        ispfccdbz40 = ispfccdbz40[ispfccdbz40 != fillvalue]
                                        if len(ispfccdbz40) > 0:
                                            radar_ccavgdbz40[it, itt] = np.nanmean(ispfccdbz40)

                                    radar_sfavgnpix[it, itt] = np.nansum(spfsfnpix[0:nradar_save])
                                    if radar_sfavgnpix[it, itt] != fillvalue:
                                        radar_sfavgrainrate[it, itt] = np.nanmean(spfsfrainrate[np.where(spfrainrate[0:nradar_save] != fillvalue)])

                else:
                    print('One or both files do not exist: ' + cloudidfilename + ', ' + pfdata_filename)
                                    
            else:
                print(ittdatetimestring)
                print('Half-hourly data ?!:' + str(ittdatetimestring))

    ###################################
    # Convert number of pixels to area
    radar_pfdbz40area = np.multiply(radar_pfdbz40npix, np.square(pixel_radius))
    radar_pfdbz45area = np.multiply(radar_pfdbz45npix, np.square(pixel_radius))
    radar_pfdbz50area = np.multiply(radar_pfdbz50npix, np.square(pixel_radius))
    radar_pfarea = np.multiply(radar_pfnpix, np.square(pixel_radius))
    radar_ccavgarea = np.multiply(radar_ccavgnpix, np.square(pixel_radius))
    radar_sfavgarea = np.multiply(radar_sfavgnpix, np.square(pixel_radius))
    radar_ccarea = np.multiply(radar_ccnpix, np.square(pixel_radius))

    ##################################
    # Save output to netCDF file

    # Definte xarray dataset
    output_data = xr.Dataset({'mcs_length':(['track'], np.squeeze(ir_mcslength)), \
                              'length': (['track'], ir_tracklength), \
                              'mcs_type': (['track'], ir_type), \
                              'status': (['track', 'time'], ir_status), \
                              'startstatus': (['track'], ir_startstatus), \
                              'endstatus': (['track'], ir_endstatus), \
                              'interruptions': (['track'], ir_interruptions), \
                              'boundary': (['track'], ir_boundary), \
                              'basetime': (['track', 'time'], ir_basetime), \
                              'datetimestring': (['track', 'time', 'characters'], ir_datetimestring), \
                              'meanlat': (['track', 'time'], ir_meanlat), \
                              'meanlon': (['track', 'time'], ir_meanlon), \
                              'core_area': (['track', 'time'], ir_corearea), \
                              'ccs_area': (['track', 'time'], ir_ccsarea), \
                              'cloudnumber': (['track', 'time'], ir_cloudnumber), \
                              'mergecloudnumber': (['track', 'time', 'mergesplit'], ir_mergecloudnumber), \
                              'splitcloudnumber': (['track', 'time', 'mergesplit'], ir_splitcloudnumber), \
                              'nmq_frac': (['track', 'time'], radar_pffrac), \
                              'npf': (['track', 'time'], radar_npf), \
                              'pf_area': (['track', 'time', 'pfs'], radar_pfarea), \
                              'pf_lon': (['track', 'time', 'pfs'], radar_pflon), \
                              'pf_lat': (['track', 'time', 'pfs'], radar_pflat), \
                              'pf_rainrate': (['track', 'time', 'pfs'], radar_pfrainrate), \
                              'pf_skewness': (['track', 'time', 'pfs'], radar_pfskewness), \
                              'pf_majoraxislength': (['track', 'time', 'pfs'], radar_pfmajoraxis), \
                              'pf_minoraxislength': (['track', 'time', 'pfs'], radar_pfminoraxis), \
                              'pf_aspectratio': (['track', 'time', 'pfs'], radar_pfaspectratio), \
                              'pf_eccentricity': (['track', 'time', 'pfs'], radar_pfeccentricity), \
                              'pf_orientation': (['track', 'time', 'pfs'], radar_pforientation), \
                              'pf_dbz40area': (['track', 'time', 'pfs'], radar_pfdbz40area), \
                              'pf_dbz45area': (['track', 'time', 'pfs'], radar_pfdbz45area), \
                              'pf_dbz50area': (['track', 'time', 'pfs'], radar_pfdbz50area), \
                              'pf_ccrainrate': (['track', 'time'], radar_ccavgrainrate), \
                              'pf_sfrainrate': (['track', 'time'], radar_sfavgrainrate), \
                              'pf_ccarea': (['track', 'time'], radar_ccavgarea), \
                              'pf_sfarea': (['track', 'time'], radar_sfavgarea), \
                              'pf_ccdbz10': (['track', 'time'], radar_ccavgdbz10), \
                              'pf_ccdbz20': (['track', 'time'], radar_ccavgdbz20), \
                              'pf_ccdbz30': (['track', 'time'], radar_ccavgdbz30), \
                              'pf_ccdbz40': (['track', 'time'], radar_ccavgdbz40), \
                              'pf_ncores': (['track', 'time'], radar_ccncores), \
                              'pf_corelon': (['track', 'time', 'cores'], radar_cclon), \
                              'pf_corelat': (['track', 'time', 'cores'], radar_cclat), \
                              'pf_corearea': (['track', 'time', 'cores'], radar_ccarea), \
                              'pf_coremajoraxislength': (['track', 'time', 'cores'], radar_ccmajoraxis), \
                              'pf_coreminoraxislength': (['track', 'time', 'cores'], radar_ccmajoraxis), \
                              'pf_coreaspectratio': (['track', 'time', 'cores'], radar_ccaspectratio), \
                              'pf_coreeccentricity': (['track', 'time', 'cores'], radar_cceccentricity), \
                              'pf_coreorientation': (['track', 'time', 'cores'], radar_ccorientation), \
                              'pf_coremaxdbz10': (['track', 'time', 'cores'], radar_ccmaxdbz10), \
                              'pf_coremaxdbz20': (['track', 'time', 'cores'], radar_ccmaxdbz20), \
                              'pf_coremaxdbz30': (['track', 'time', 'cores'], radar_ccmaxdbz30), \
                              'pf_coremaxdbz40': (['track', 'time', 'cores'], radar_ccmaxdbz40), \
                              'pf_coreavgdbz10': (['track', 'time', 'cores'], radar_ccdbz10mean), \
                              'pf_coreavgdbz20': (['track', 'time', 'cores'], radar_ccdbz20mean), \
                              'pf_coreavgdbz30': (['track', 'time', 'cores'], radar_ccdbz30mean), \
                              'pf_coreavgdbz40': (['track', 'time', 'cores'], radar_ccdbz40mean)}, \
                             coords={'track': (['track'], np.arange(1, ir_ntracks+1)), \
                                     'time': (['time'], np.arange(0, ir_nmaxlength)), \
                                     'pfs':(['pfs'], np.arange(0, nmaxpf)), \
                                     'cores': (['cores'], np.arange(0, nmaxcore)), \
                                     'mergesplit': (['mergesplit'], np.arange(0, nmaxclouds)), \
                                     'characters': (['characters'], np.ones(13)*fillvalue)}, \
                             attrs={'title':'File containing ir and precpitation statistics for each track', \
                                    'source1':irdatasource, \
                                    'source2':nmqdatasource, \
                                    'description':datadescription, \
                                    'startdate':startdate, \
                                    'enddate':enddate, \
                                    '_FillValue':str(int(fillvalue)), \
                                    'time_resolution_hour':str(int(datatimeresolution)), \
                                    'mergdir_pixel_radius':pixel_radius, \
                                    'MCS_IR_area_thresh_km2':str(int(mcs_irareathresh)), \
                                    'MCS_IR_duration_thresh_hr':str(int(mcs_irdurationthresh)), \
                                    'MCS_IR_eccentricity_thres':str(int(mcs_ireccentricitythresh)), \
                                    'max_number_pfs':str(int(nmaxpf)), \
                                    'contact':'Hannah C Barnes: hannah.barnes@pnnl.gov', \
                                    'created_on':time.ctime(time.time())})

    # Specify variable attributes
    output_data.track.attrs['description'] =  'Total number of tracked features'
    output_data.track.attrs['units'] = 'unitless'

    output_data.time.attrs['dscription'] = 'Maximum number of features in a given track'
    output_data.time.attrs['units'] = 'unitless'

    output_data.pfs.attrs['long_name'] = 'Maximum number of precipitation features in one cloud feature'
    output_data.pfs.attrs['units'] = 'unitless'

    output_data.cores.attrs['long_name'] = 'Maximum number of convective cores in a precipitation feature at one time'
    output_data.cores.attrs['units'] = 'unitless'

    output_data.mergesplit.attrs['long_name'] = 'Maximum number of mergers / splits at one time'
    output_data.mergesplit.attrs['units'] = 'unitless'

    output_data.length.attrs['long_name'] = 'Length of track containing each track'
    output_data.length.attrs['units'] = 'Temporal resolution of orginal data'
    output_data.length.attrs['_FillValue'] = fillvalue

    output_data.mcs_length.attrs['long_name'] = 'Length of each MCS in each track'
    output_data.mcs_length.attrs['units'] = 'Temporal resolution of orginal data'
    output_data.mcs_length.attrs['_FillValue'] = fillvalue

    output_data.mcs_type.attrs['long_name'] = 'Type of MCS'
    output_data.mcs_type.attrs['values'] = '1 = MCS, 2 = Squall line'
    output_data.mcs_type.attrs['units'] = 'unitless'
    output_data.mcs_type.attrs['_FillValue'] = fillvalue

    output_data.status.attrs['long_name'] = 'Flag indicating the status of each feature in MCS'
    output_data.status.attrs['values'] = '-9999=missing cloud or cloud removed due to short track, 0=track ends here, 1=cloud continues as one cloud in next file, 2=Biggest cloud in merger, 21=Smaller cloud(s) in merger, 13=Cloud that splits, 3=Biggest cloud from a split that stops after the split, 31=Smaller cloud(s) from a split that stop after the split. The last seven classifications are added together in different combinations to describe situations.'
    output_data.status.attrs['min_value'] = 0
    output_data.status.attrs['max_value'] = 52
    output_data.status.attrs['units'] = 'unitless'
    output_data.status.attrs['_FillValue'] = fillvalue

    output_data.startstatus.attrs['long_name'] = 'Flag indicating the status of first feature in MCS track'
    output_data.startstatus.attrs['values'] = '-9999=missing cloud or cloud removed due to short track, 0=track ends here, 1=cloud continues as one cloud in next file, 2=Biggest cloud in merger, 21=Smaller cloud(s) in merger, 13=Cloud that splits, 3=Biggest cloud from a split that stops after the split, 31=Smaller cloud(s) from a split that stop after the split. The last seven classifications are added together in different combinations to describe situations.'
    output_data.startstatus.attrs['min_value'] = 0
    output_data.startstatus.attrs['max_value'] = 52
    output_data.startstatus.attrs['units'] = 'unitless'
    output_data.startstatus.attrs['_FillValue'] = fillvalue

    output_data.endstatus.attrs['long_name'] = 'Flag indicating the status of last feature in MCS track'
    output_data.endstatus.attrs['values'] = '-9999=missing cloud or cloud removed due to short track, 0=track ends here, 1=cloud continues as one cloud in next file, 2=Biggest cloud in merger, 21=Smaller cloud(s) in merger, 13=Cloud that splits, 3=Biggest cloud from a split that stops after the split, 31=Smaller cloud(s) from a split that stop after the split. The last seven classifications are added together in different combinations to describe situations.'
    output_data.endstatus.attrs['min_value'] = 0
    output_data.endstatus.attrs['max_value'] = 52
    output_data.endstatus.attrs['units'] = 'unitless'
    output_data.endstatus.attrs['_FillValue'] = fillvalue

    output_data.interruptions.attrs['long_name'] = 'flag indicating if track incomplete'
    output_data.interruptions.attrs['values'] = '0 = full track available, good data. 1 = track starts at first file, track cut short by data availability. 2 = track ends at last file, track cut short by data availability'
    output_data.interruptions.attrs['min_value'] = 0
    output_data.interruptions.attrs['max_value'] = 2
    output_data.interruptions.attrs['units'] = 'unitless'
    output_data.interruptions.attrs['_FillValue'] = fillvalue

    output_data.boundary.attrs['long_name'] = 'Flag indicating whether the core + cold anvil touches one of the domain edges.'
    output_data.boundary.attrs['values'] = '0 = away from edge. 1= touches edge.'
    output_data.boundary.attrs['min_value'] = 0
    output_data.boundary.attrs['max_value'] = 1
    output_data.boundary.attrs['units'] = 'unitless'
    output_data.boundary.attrs['_FillValue'] = fillvalue

    output_data.basetime.attrs['standard_name'] = 'time'
    output_data.basetime.attrs['long_name'] = 'basetime of cloud at the given time'
    output_data.basetime.attrs['units'] = 'seconds since 01/01/1970 00:00'
    output_data.basetime.attrs['_FillValue'] = fillvalue

    output_data.datetimestring.attrs['long_name'] = 'date-time'
    output_data.datetimestring.attrs['long_name'] = 'date_time for each cloud in the mcs'

    output_data.meanlon.attrs['standard_name'] = 'longitude'
    output_data.meanlon.attrs['long_name'] = 'mean longitude of the core + cold anvil for each feature at the given time'
    output_data.meanlon.attrs['min_value'] = geolimits[1]
    output_data.meanlon.attrs['max_value'] = geolimits[3]
    output_data.meanlon.attrs['units'] = 'degrees'
    output_data.meanlon.attrs['_FillValue'] = fillvalue

    output_data.meanlat.attrs['standard_name'] = 'latitude'
    output_data.meanlat.attrs['long_name'] = 'mean latitude of the core + cold anvil for each feature at the given time'
    output_data.meanlat.attrs['min_value'] = geolimits[0]
    output_data.meanlat.attrs['max_value'] = geolimits[2]
    output_data.meanlat.attrs['units'] = 'degrees'
    output_data.meanlat.attrs['_FillValue'] = fillvalue

    output_data.core_area.attrs['long_name'] = 'area of the cold core at the given time'
    output_data.core_area.attrs['units'] = 'km^2'
    output_data.core_area.attrs['_FillValue'] = fillvalue

    output_data.ccs_area.attrs['long_name'] = 'area of the cold core and cold anvil at the given time'
    output_data.ccs_area.attrs['units'] = 'km^2'
    output_data.ccs_area.attrs['_FillValue'] = fillvalue

    output_data.cloudnumber.attrs['long_name'] = 'cloud number in the corresponding cloudid file of clouds in the mcs'
    output_data.cloudnumber.attrs['usage'] = 'to link this tracking statistics file with pixel-level cloudid files, use the cloudidfile and cloudnumber together to identify which cloud this current track and time is associated with'
    output_data.cloudnumber.attrs['units'] = 'unitless'
    output_data.cloudnumber.attrs['_FillValue'] = fillvalue

    output_data.mergecloudnumber.attrs['long_name'] = 'cloud number of small, short-lived clouds merging into the MCS'
    output_data.mergecloudnumber.attrs['usage'] = 'to link this tracking statistics file with pixel-level cloudid files, use the cloudidfile and cloudnumber together to identify which cloud this current track and time is associated with'
    output_data.mergecloudnumber.attrs['units'] = 'unitless'
    output_data.mergecloudnumber.attrs['_FillValue'] = fillvalue

    output_data.splitcloudnumber.attrs['long_name'] = 'cloud number of small, short-lived clouds splitting from the MCS'
    output_data.splitcloudnumber.attrs['usage'] = 'to link this tracking statistics file with pixel-level cloudid files, use the cloudidfile and cloudnumber together to identify which cloud this current track and time is associated with'
    output_data.splitcloudnumber.attrs['units'] = 'unitless'
    output_data.splitcloudnumber.attrs['_FillValue'] = fillvalue

    output_data.nmq_frac.attrs['long_name'] = 'fraction of cold cloud shielf covered by NMQ mask'
    output_data.nmq_frac.attrs['units'] = 'unitless'
    output_data.nmq_frac.attrs['min_value'] = 0
    output_data.nmq_frac.attrs['max_value'] = 1
    output_data.nmq_frac.attrs['units'] = 'unitless'
    output_data.nmq_frac.attrs['_FillValue'] = fillvalue

    output_data.npf.attrs['long_name'] = 'number of precipitation features at a given time'
    output_data.npf.attrs['units'] = 'unitless'
    output_data.npf.attrs['_FillValue'] = fillvalue

    output_data.pf_area.attrs['long_name'] = 'area of each precipitation feature at a given time'
    output_data.pf_area.attrs['units'] = 'km^2'
    output_data.pf_area.attrs['_FillValue'] = fillvalue

    output_data.pf_lon.attrs['standard_name'] = 'longitude'
    output_data.pf_lon.attrs['long_name'] = 'mean longitude of each precipitaiton feature at a given time'
    output_data.pf_lon.attrs['units'] = 'degrees'
    output_data.pf_lon.attrs['_FillValue'] = fillvalue

    output_data.pf_lat.attrs['standard_name'] = 'latitude'
    output_data.pf_lat.attrs['long_name'] = 'mean latitude of each precipitaiton feature at a given time'
    output_data.pf_lat.attrs['units'] = 'degrees'
    output_data.pf_lat.attrs['_FillValue'] = fillvalue

    output_data.pf_rainrate.attrs['long_name'] = 'mean precipitation rate (from rad_hsr_1h) pf each precipitation feature at a given time'
    output_data.pf_rainrate.attrs['units'] = 'mm/hr'
    output_data.pf_rainrate.attrs['_FillValue'] = fillvalue

    output_data.pf_skewness.attrs['long_name'] = 'skewness of each precipitation feature at a given time'
    output_data.pf_skewness.attrs['units'] = 'unitless'
    output_data.pf_skewness.attrs['_FillValue'] = fillvalue

    output_data.pf_majoraxislength.attrs['long_name'] = 'major axis length of each precipitation feature at a given time'
    output_data.pf_majoraxislength.attrs['units'] = 'km'
    output_data.pf_majoraxislength.attrs['_FillValue'] = fillvalue

    output_data.pf_minoraxislength.attrs['long_name'] = 'minor axis length of each precipitation feature at a given time'
    output_data.pf_minoraxislength.attrs['units'] = 'km'
    output_data.pf_minoraxislength.attrs['_FillValue'] = fillvalue

    output_data.pf_aspectratio.attrs['long_name'] = 'aspect ratio (major axis / minor axis) of each precipitation feature at a given time'
    output_data.pf_aspectratio.attrs['units'] = 'unitless'
    output_data.pf_aspectratio.attrs['_FillValue'] = fillvalue

    output_data.pf_eccentricity.attrs['long_name'] = 'eccentricity of each precipitation feature at a given time'
    output_data.pf_eccentricity.attrs['min_value'] = 0
    output_data.pf_eccentricity.attrs['max_value'] = 1
    output_data.pf_eccentricity.attrs['units'] = 'unitless'
    output_data.pf_eccentricity.attrs['_FillValue']= fillvalue

    output_data.pf_orientation.attrs['long_name'] = 'orientation of the major axis of each precipitation feature at a given time'
    output_data.pf_orientation.attrs['units'] = 'degrees clockwise from vertical'
    output_data.pf_orientation.attrs['min_value'] = 0
    output_data.pf_orientation.attrs['max_value'] = 360
    output_data.pf_orientation.attrs['_FillValue'] = fillvalue

    output_data.pf_dbz40area.attrs['long_name'] = 'area of the precipitation feature with column maximum reflectivity >= 40 dBZ at a given time'
    output_data.pf_dbz40area.attrs['units'] = 'km^2'
    output_data.pf_dbz40area.attrs['_FillValue'] = fillvalue

    output_data.pf_dbz45area.attrs['long_name'] = 'area of the precipitation feature with column maximum reflectivity >= 45 dBZ at a given time'
    output_data.pf_dbz45area.attrs['units'] = 'km^2'
    output_data.pf_dbz45area.attrs['_FillValue'] = fillvalue

    output_data.pf_dbz50area.attrs['long_name'] = 'area of the precipitation feature with column maximum reflectivity >= 50 dBZ at a given time'
    output_data.pf_dbz50area.attrs['units'] = 'km^2'
    output_data.pf_dbz50area.attrs['_FillValue'] = fillvalue

    output_data.pf_ccrainrate.attrs['long_name'] = 'mean rain rate of the largest several the convective cores at a given time'
    output_data.pf_ccrainrate.attrs['units'] = 'mm/hr'
    output_data.pf_ccrainrate.attrs['_FillValue'] = fillvalue

    output_data.pf_sfrainrate.attrs['long_name'] = 'mean rain rate in the largest several statiform regions at a given time'
    output_data.pf_sfrainrate.attrs['units'] = 'mm/hr'
    output_data.pf_sfrainrate.attrs['_FillValue'] = fillvalue

    output_data.pf_ccarea.attrs['long_name'] = 'total area of the largest several convective cores at a given time'
    output_data.pf_ccarea.attrs['units'] = 'km^2'
    output_data.pf_ccarea.attrs['_FillValue'] = fillvalue

    output_data.pf_sfarea.attrs['long_name'] = 'total area of the largest several stratiform regions at a given time'
    output_data.pf_sfarea.attrs['units'] = 'km^2'
    output_data.pf_sfarea.attrs['_FillValue'] = fillvalue

    output_data.pf_ccdbz10.attrs['long_name'] = 'mean 10 dBZ echo top height of the largest several convective cores at a given time'
    output_data.pf_ccdbz10.attrs['units'] = 'km'
    output_data.pf_ccdbz10.attrs['_FillValue'] = fillvalue

    output_data.pf_ccdbz20.attrs['long_name'] = 'mean 20 dBZ echo top height of the largest several convective cores at a given time'
    output_data.pf_ccdbz20.attrs['units'] = 'km'
    output_data.pf_ccdbz20.attrs['_FillValue'] = fillvalue

    output_data.pf_ccdbz30.attrs['long_name'] = 'mean 30 dBZ echo top height the largest several convective cores at a given time'
    output_data.pf_ccdbz30.attrs['units'] = 'km'
    output_data.pf_ccdbz30.attrs['_FillValue'] = fillvalue

    output_data.pf_ccdbz40.attrs['long_name'] = 'mean 40 dBZ echo top height of the largest several convective cores at a given time'
    output_data.pf_ccdbz40.attrs['units'] = 'km'
    output_data.pf_ccdbz40.attrs['_FillValue'] = fillvalue

    output_data.pf_ncores.attrs['long_name'] = 'number of convective cores (radar identified) in a precipitation feature at a given time'
    output_data.pf_ncores.attrs['units'] = 'unitless'
    output_data.pf_ncores.attrs['_FillValue'] = fillvalue

    output_data.pf_corelon.attrs['standard_name'] = 'longitude'
    output_data.pf_corelon.attrs['long_name'] = 'mean longitude of each convective core in a precipitation features at the given time'
    output_data.pf_corelon.attrs['units'] = 'degrees'
    output_data.pf_corelon.attrs['_FillValue'] = fillvalue

    output_data.pf_coreeccentricity.attrs['long_name'] = 'eccentricity of each convective core in the precipitation feature at a given time'
    output_data.pf_coreeccentricity.attrs['min_value'] = 0
    output_data.pf_coreeccentricity.attrs['max_value'] = 1
    output_data.pf_coreeccentricity.attrs['units'] = 'unitless'
    output_data.pf_coreeccentricity.attrs['_FillValue']= fillvalue

    output_data.pf_orientation.attrs['long_name'] = 'orientation of the major axis of each precipitation feature at a given time'
    output_data.pf_orientation.attrs['units'] = 'degrees clockwise from vertical'
    output_data.pf_orientation.attrs['min_value'] = 0
    output_data.pf_orientation.attrs['max_value'] = 360
    output_data.pf_orientation.attrs['_FillValue'] = fillvalue

    output_data.pf_corelat.attrs['standard_name'] = 'latitude'
    output_data.pf_corelat.attrs['long_name'] = 'mean latitude of each convective core in a precipitation features at the given time'
    output_data.pf_corelat.attrs['units'] = 'degrees'
    output_data.pf_corelat.attrs['_FillValue'] = fillvalue

    output_data.pf_corearea.attrs['long_name'] = 'area of each convective core in the precipitatation feature at the given time'
    output_data.pf_corearea.attrs['units'] = 'km^2'
    output_data.pf_corearea.attrs['_FillValue'] = fillvalue

    output_data.pf_coremajoraxislength.attrs['long_name'] = 'major axis length of each convective core in the precipitation feature at a given time'
    output_data.pf_coremajoraxislength.attrs['units'] = 'km'
    output_data.pf_coremajoraxislength.attrs['_FillValue'] = fillvalue

    output_data.pf_coreminoraxislength.attrs['long_name'] = 'minor axis length of each convective core in the precipitation feature at a given time'
    output_data.pf_coreminoraxislength.attrs['units'] = 'km'
    output_data.pf_coreminoraxislength.attrs['_FillValue'] = fillvalue

    output_data.pf_coreaspectratio.attrs['long_name'] = 'aspect ratio (major / minor axis length) of each convective core in the precipitation feature at a given time'
    output_data.pf_coreaspectratio.attrs['units'] = 'unitless'
    output_data.pf_coreaspectratio.attrs['_FillValue'] = fillvalue

    output_data.pf_coreeccentricity.attrs['long_name'] = 'eccentricity of each convective core in the precipitation feature at a given time'
    output_data.pf_coreeccentricity.attrs['min_value'] = 0
    output_data.pf_coreeccentricity.attrs['max_value'] = 1
    output_data.pf_coreeccentricity.attrs['units'] = 'unitless'
    output_data.pf_coreeccentricity.attrs['_FillValue']= fillvalue

    output_data.pf_coreorientation.attrs['long_name'] = 'orientation of the major axis of each convective core in the precipitation feature at a given time'
    output_data.pf_coreorientation.attrs['units'] = 'degrees clockwise from vertical'
    output_data.pf_coreorientation.attrs['min_value'] = 0
    output_data.pf_coreorientation.attrs['max_value'] = 360
    output_data.pf_coreorientation.attrs['_FillValue'] = fillvalue

    output_data.pf_coremaxdbz10.attrs['long_name'] = 'maximum 10-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coremaxdbz10.attrs['units'] = 'km'
    output_data.pf_coremaxdbz10.attrs['_FillValue'] = fillvalue

    output_data.pf_coremaxdbz20.attrs['long_name'] = 'maximum 20-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coremaxdbz20.attrs['units'] = 'km'
    output_data.pf_coremaxdbz20.attrs['_FillValue'] = fillvalue

    output_data.pf_coremaxdbz30.attrs['long_name'] = 'maximum 30-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coremaxdbz30.attrs['units'] = 'km'
    output_data.pf_coremaxdbz30.attrs['_FillValue'] = fillvalue

    output_data.pf_coremaxdbz40.attrs['long_name'] = 'maximum 40-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coremaxdbz40.attrs['units'] = 'km'
    output_data.pf_coremaxdbz40.attrs['_FillValue'] = fillvalue

    output_data.pf_coreavgdbz10.attrs['long_name'] = 'mean 10-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coreavgdbz10.attrs['units'] = 'km'
    output_data.pf_coreavgdbz10.attrs['_FillValue'] = fillvalue

    output_data.pf_coreavgdbz20.attrs['long_name'] = 'mean 20-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coreavgdbz20.attrs['units'] = 'km'
    output_data.pf_coreavgdbz20.attrs['_FillValue'] = fillvalue

    output_data.pf_coreavgdbz30.attrs['long_name'] = 'mean 30-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coreavgdbz30.attrs['units'] = 'km'
    output_data.pf_coreavgdbz30.attrs['_FillValue'] = fillvalue

    output_data.pf_coreavgdbz40.attrs['long_name'] = 'mean 40-dBZ echo top height in each convective core in the precipitation features at a given time'
    output_data.pf_coreavgdbz40.attrs['units'] = 'km'
    output_data.pf_coreavgdbz40.attrs['_FillValue'] = fillvalue

    # Write netcdf file
    print('')
    print(statistics_outfile)
    output_data.to_netcdf(path=statistics_outfile, mode='w', format='NETCDF4_CLASSIC', unlimited_dims='track', encoding={'mcs_length': {'zlib':True}, 'mcs_type': {'zlib':True}, 'status': {'zlib':True}, 'startstatus': {'zlib':True}, 'endstatus': {'zlib':True}, 'basetime': {'zlib':True}, 'datetimestring': {'zlib':True}, 'meanlat': {'zlib':True}, 'meanlon': {'zlib':True}, 'core_area': {'zlib':True}, 'ccs_area': {'zlib':True}, 'cloudnumber': {'zlib':True}, 'mergecloudnumber': {'zlib':True}, 'splitcloudnumber': {'zlib':True}, 'nmq_frac': {'zlib':True}, 'pf_area': {'zlib':True}, 'pf_lon': {'zlib':True}, 'pf_lat': {'zlib':True}, 'pf_rainrate': {'zlib':True}, 'pf_skewness': {'zlib':True}, 'pf_majoraxislength': {'zlib':True}, 'pf_minoraxislength': {'zlib':True}, 'pf_aspectratio': {'zlib':True}, 'pf_orientation': {'zlib':True}, 'pf_eccentricity': {'zlib':True}, 'pf_dbz40area': {'zlib':True}, 'pf_dbz45area': {'zlib':True}, 'pf_dbz50area': {'zlib':True}, 'pf_ccarea': {'zlib':True}, 'pf_sfarea': {'zlib':True}, 'pf_ccrainrate': {'zlib':True}, 'pf_sfrainrate': {'zlib':True}, 'pf_ccdbz10': {'zlib':True}, 'pf_ccdbz20': {'zlib':True}, 'pf_ccdbz30': {'zlib':True}, 'pf_ccdbz40': {'zlib':True}, 'pf_ncores': {'zlib':True}, 'pf_corelon': {'zlib':True}, 'pf_corelat': {'zlib':True}, 'pf_corearea': {'zlib':True}, 'pf_coremajoraxislength': {'zlib':True},'pf_minoraxislength': {'zlib':True}, 'pf_coreaspectratio': {'zlib':True}, 'pf_coreorientation': {'zlib':True}, 'pf_coreeccentricity': {'zlib':True}, 'pf_coremaxdbz10': {'zlib':True}, 'pf_coremaxdbz20': {'zlib':True}, 'pf_coremaxdbz30': {'zlib':True}, 'pf_coremaxdbz40': {'zlib':True}, 'pf_coreavgdbz10': {'zlib':True}, 'pf_coreavgdbz20': {'zlib':True},  'pf_coreavgdbz30': {'zlib':True}, 'pf_coreavgdbz40': {'zlib':True}})
    
